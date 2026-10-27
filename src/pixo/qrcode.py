"""Gerador de QR Code (ISO/IEC 18004) feito do zero, sem dependências.

Etapas:
1. Escolher a menor versão (tamanho 21x21 até 177x177) em que o texto cabe.
2. Montar os bits: modo "byte" + quantidade de bytes + os bytes + preenchimento.
3. Dividir em blocos e calcular a correção de erros de cada um (Reed-Solomon sobre GF(256)):
   é isso que deixa o QR ser lido mesmo amassado, sujo ou com um logo por cima.
4. Desenhar os padrões fixos (os três quadrados dos cantos, alinhamento, linhas de tempo)
   e preencher o resto em zigue-zague com os dados.
5. Testar as 8 máscaras e ficar com a que deixa o desenho mais fácil de ler
   (menos blocos grandes da mesma cor, menos padrões parecidos com os quadrados dos cantos).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Correcao(Enum):
    """Quanto do QR pode ser danificado e ele ainda ser lido."""

    L = (0, 1)  # ~7%
    M = (1, 0)  # ~15%  (o padrão para Pix)
    Q = (2, 3)  # ~25%
    H = (3, 2)  # ~30%

    @property
    def indice(self) -> int:
        return self.value[0]

    @property
    def bits_formato(self) -> int:
        return self.value[1]


# Tabelas da norma, por nível de correção (L, M, Q, H) e versão (1 a 40). Índice 0 não é usado.
CODEWORDS_CORRECAO_POR_BLOCO = (
    (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
)
NUMERO_DE_BLOCOS = (
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
)


class TextoGrandeDemais(ValueError):
    pass


# ---------- Reed-Solomon sobre GF(2^8) ----------


def _gf_mul(x: int, y: int) -> int:
    """Multiplicação no corpo finito GF(256) com o polinômio x^8 + x^4 + x^3 + x^2 + 1 (0x11D)."""
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(grau: int) -> list[int]:
    """Polinômio gerador: (x - r^0)(x - r^1)...(x - r^(grau-1)), com r = 2."""
    resultado = [0] * (grau - 1) + [1]
    raiz = 1
    for _ in range(grau):
        for j in range(grau):
            resultado[j] = _gf_mul(resultado[j], raiz)
            if j + 1 < grau:
                resultado[j] ^= resultado[j + 1]
        raiz = _gf_mul(raiz, 0x02)
    return resultado


def _rs_resto(dados: list[int], divisor: list[int]) -> list[int]:
    """Resto da divisão dos dados pelo gerador = os bytes de correção."""
    resultado = [0] * len(divisor)
    for b in dados:
        fator = b ^ resultado.pop(0)
        resultado.append(0)
        for i, coef in enumerate(divisor):
            resultado[i] ^= _gf_mul(coef, fator)
    return resultado


# ---------- Capacidade ----------


def _modulos_de_dados(versao: int) -> int:
    """Quantos módulos sobram para dados depois dos padrões fixos."""
    total = (16 * versao + 128) * versao + 64
    if versao >= 2:
        n = versao // 7 + 2
        total -= (25 * n - 10) * n - 55
        if versao >= 7:
            total -= 36
    return total


def _codewords_de_dados(versao: int, correcao: Correcao) -> int:
    e = correcao.indice
    return _modulos_de_dados(versao) // 8 - CODEWORDS_CORRECAO_POR_BLOCO[e][versao] * NUMERO_DE_BLOCOS[e][versao]


def _bits_contagem(versao: int) -> int:
    return 8 if versao <= 9 else 16


def capacidade(versao: int, correcao: Correcao = Correcao.M) -> int:
    """Quantos bytes cabem nessa versão (modo byte)."""
    return (_codewords_de_dados(versao, correcao) * 8 - 4 - _bits_contagem(versao)) // 8


# ---------- QR Code ----------


@dataclass
class QRCode:
    versao: int
    correcao: Correcao
    mascara: int
    modulos: list[list[bool]]  # True = quadradinho escuro

    @property
    def tamanho(self) -> int:
        return len(self.modulos)


def gerar_qr(texto: str | bytes, correcao: Correcao = Correcao.M, mascara: int | None = None) -> QRCode:
    """Gera o QR Code de um texto.

    >>> qr = gerar_qr("Olá, Pix!")
    >>> qr.versao, qr.tamanho
    (1, 21)
    """
    dados = texto.encode("utf-8") if isinstance(texto, str) else texto
    for versao in range(1, 41):
        if len(dados) <= capacidade(versao, correcao):
            break
    else:
        raise TextoGrandeDemais(f"Texto com {len(dados)} bytes não cabe num QR Code (máximo {capacidade(40, correcao)}).")

    codewords = _adicionar_correcao(_bits_de_dados(dados, versao, correcao), versao, correcao)
    desenho = _Desenho(versao)
    desenho.padroes_fixos()
    desenho.dados(codewords)

    if mascara is None:
        mascara = min(range(8), key=lambda m: desenho.penalidade_com(m, correcao))
    desenho.aplicar_mascara(mascara)
    desenho.formato(correcao, mascara)
    return QRCode(versao, correcao, mascara, desenho.modulos)


def _bits_de_dados(dados: bytes, versao: int, correcao: Correcao) -> list[int]:
    bits: list[int] = []

    def anexar(valor: int, n: int) -> None:
        bits.extend((valor >> i) & 1 for i in reversed(range(n)))

    anexar(0b0100, 4)  # modo byte
    anexar(len(dados), _bits_contagem(versao))
    for b in dados:
        anexar(b, 8)

    capacidade_bits = _codewords_de_dados(versao, correcao) * 8
    anexar(0, min(4, capacidade_bits - len(bits)))  # terminador
    anexar(0, -len(bits) % 8)  # completa o último byte
    resultado = [int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits), 8)]
    preenchimento = 0xEC  # a norma manda alternar 0xEC e 0x11 até encher
    while len(resultado) < capacidade_bits // 8:
        resultado.append(preenchimento)
        preenchimento ^= 0xEC ^ 0x11
    return resultado


def _adicionar_correcao(dados: list[int], versao: int, correcao: Correcao) -> list[int]:
    """Divide os dados em blocos, calcula a correção de cada um e intercala tudo."""
    e = correcao.indice
    n_blocos = NUMERO_DE_BLOCOS[e][versao]
    tam_correcao = CODEWORDS_CORRECAO_POR_BLOCO[e][versao]
    total = _modulos_de_dados(versao) // 8
    n_curtos = n_blocos - total % n_blocos
    tam_curto = total // n_blocos

    divisor = _rs_divisor(tam_correcao)
    blocos: list[list[int]] = []
    k = 0
    for i in range(n_blocos):
        n = tam_curto - tam_correcao + (0 if i < n_curtos else 1)
        bloco = dados[k : k + n]
        k += n
        correcao_bloco = _rs_resto(bloco, divisor)
        if i < n_curtos:
            bloco = bloco + [0]  # só para alinhar; esse byte é pulado ao intercalar
        blocos.append(bloco + correcao_bloco)

    # Intercala: 1º byte de cada bloco, depois o 2º de cada bloco... (um arranhão não
    # destrói um bloco inteiro, espalha o estrago entre vários).
    resultado = []
    for i in range(len(blocos[0])):
        for j, bloco in enumerate(blocos):
            if i != tam_curto - tam_correcao or j >= n_curtos:
                resultado.append(bloco[i])
    return resultado


_MASCARAS = (
    lambda x, y: (x + y) % 2 == 0,
    lambda x, y: y % 2 == 0,
    lambda x, y: x % 3 == 0,
    lambda x, y: (x + y) % 3 == 0,
    lambda x, y: (x // 3 + y // 2) % 2 == 0,
    lambda x, y: x * y % 2 + x * y % 3 == 0,
    lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
    lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
)


class _Desenho:
    def __init__(self, versao: int):
        self.versao = versao
        self.tamanho = versao * 4 + 17
        self.modulos = [[False] * self.tamanho for _ in range(self.tamanho)]
        self.fixo = [[False] * self.tamanho for _ in range(self.tamanho)]

    def _fixar(self, x: int, y: int, escuro: bool) -> None:
        self.modulos[y][x] = escuro
        self.fixo[y][x] = True

    def padroes_fixos(self) -> None:
        t = self.tamanho
        for i in range(t):  # linhas de tempo: alternam escuro/claro
            self._fixar(6, i, i % 2 == 0)
            self._fixar(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (t - 4, 3), (3, t - 4)):  # os três quadrados dos cantos
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < t and 0 <= y < t:
                        self._fixar(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self._posicoes_alinhamento()
        n = len(pos)
        for i in range(n):
            for j in range(n):
                if (i, j) in ((0, 0), (0, n - 1), (n - 1, 0)):
                    continue  # coincidem com os quadrados dos cantos
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._fixar(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
        self.formato(Correcao.M, 0)  # reserva o espaço; o valor certo é escrito no final
        self._versao()

    def _posicoes_alinhamento(self) -> list[int]:
        if self.versao == 1:
            return []
        n = self.versao // 7 + 2
        passo = (self.versao * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        return [6] + [self.tamanho - 7 - i * passo for i in reversed(range(n - 1))]

    def formato(self, correcao: Correcao, mascara: int) -> None:
        dados = correcao.bits_formato << 3 | mascara
        resto = dados
        for _ in range(10):
            resto = (resto << 1) ^ ((resto >> 9) * 0x537)
        bits = (dados << 10 | resto) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        t = self.tamanho
        for i in range(6):
            self._fixar(8, i, bit(i))
        self._fixar(8, 7, bit(6))
        self._fixar(8, 8, bit(7))
        self._fixar(7, 8, bit(8))
        for i in range(9, 15):
            self._fixar(14 - i, 8, bit(i))
        for i in range(8):
            self._fixar(t - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._fixar(8, t - 15 + i, bit(i))
        self._fixar(8, t - 8, True)  # o "módulo escuro", sempre presente

    def _versao(self) -> None:
        if self.versao < 7:
            return
        resto = self.versao
        for _ in range(12):
            resto = (resto << 1) ^ ((resto >> 11) * 0x1F25)
        bits = self.versao << 12 | resto
        for i in range(18):
            b = (bits >> i) & 1 == 1
            a, c = self.tamanho - 11 + i % 3, i // 3
            self._fixar(a, c, b)
            self._fixar(c, a, b)

    def dados(self, codewords: list[int]) -> None:
        """Preenche de baixo para cima, em colunas de 2, fazendo zigue-zague."""
        i = 0
        total = len(codewords) * 8
        direita = self.tamanho - 1
        while direita >= 1:
            if direita == 6:  # pula a coluna da linha de tempo
                direita = 5
            for vert in range(self.tamanho):
                for j in range(2):
                    x = direita - j
                    subindo = (direita + 1) & 2 == 0
                    y = self.tamanho - 1 - vert if subindo else vert
                    if not self.fixo[y][x] and i < total:
                        self.modulos[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            direita -= 2

    def aplicar_mascara(self, mascara: int) -> None:
        f = _MASCARAS[mascara]
        for y in range(self.tamanho):
            for x in range(self.tamanho):
                if not self.fixo[y][x] and f(x, y):
                    self.modulos[y][x] = not self.modulos[y][x]

    def penalidade_com(self, mascara: int, correcao: Correcao) -> int:
        self.aplicar_mascara(mascara)
        self.formato(correcao, mascara)
        pontos = penalidade(self.modulos)
        self.aplicar_mascara(mascara)  # aplicar de novo desfaz (é um XOR)
        return pontos


def penalidade(m: list[list[bool]]) -> int:
    """Regras da norma para "quão difícil de ler" um desenho é. Menor é melhor."""
    t = len(m)
    pontos = 0
    linhas = [m[y] for y in range(t)] + [[m[y][x] for y in range(t)] for x in range(t)]

    # 1) sequências de 5 ou mais módulos da mesma cor
    for linha in linhas:
        seq = 1
        for a, b in zip(linha, linha[1:]):
            if a == b:
                seq += 1
            else:
                if seq >= 5:
                    pontos += 3 + seq - 5
                seq = 1
        if seq >= 5:
            pontos += 3 + seq - 5

    # 2) blocos 2x2 da mesma cor
    for y in range(t - 1):
        for x in range(t - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                pontos += 3

    # 3) padrões que imitam os quadrados dos cantos (1011101 com 4 claros ao lado)
    padrao_a = (True, False, True, True, True, False, True, False, False, False, False)
    padrao_b = padrao_a[::-1]
    for linha in linhas:
        tl = tuple(linha)
        for i in range(t - 10):
            janela = tl[i : i + 11]
            if janela == padrao_a or janela == padrao_b:
                pontos += 40

    # 4) proporção de escuros longe de 50%
    escuros = sum(sum(linha) for linha in m)
    total = t * t
    k = (abs(escuros * 20 - total * 10) + total - 1) // total - 1
    pontos += k * 10
    return pontos
