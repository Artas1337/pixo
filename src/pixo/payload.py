"""O código Pix "copia e cola" (BR Code).

O BR Code segue o padrão EMV de QR Codes de pagamento: uma sequência de campos no
formato ID (2 dígitos) + TAMANHO (2 dígitos) + VALOR. Alguns campos têm subcampos
no mesmo formato. O último campo (63) é um CRC16 de tudo que vem antes: se uma
letra mudar, o banco recusa o código.

    00 02 01                       versão do formato
    26 .. 00 14 br.gov.bcb.pix     conta Pix: identificador + chave + descrição
          01 11 12345678909
    52 04 0000                     categoria do comércio (0000 = não informada)
    53 03 986                      moeda (986 = real)
    54 05 10.00                    valor (opcional)
    58 02 BR                       país
    59 .. NOME DO RECEBEDOR         até 25 caracteres
    60 .. CIDADE                    até 15 caracteres
    62 .. 05 .. TXID                identificador da cobrança (*** = sem identificador)
    63 04 ABCD                     CRC16
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .chaves import Chave, ChaveInvalida, normalizar_chave

GUI_PIX = "br.gov.bcb.pix"
LIMITE_NOME = 25
LIMITE_CIDADE = 15
LIMITE_TXID = 25
LIMITE_CONTA = 99  # o campo 26 inteiro (identificador + chave + descrição) cabe em 99 caracteres


class CodigoInvalido(ValueError):
    """O código Pix lido está quebrado. A mensagem diz onde e por quê."""


# ---------- CRC16 ----------


def crc16(dados: str) -> str:
    """CRC16-CCITT (polinômio 0x1021, valor inicial 0xFFFF), em 4 dígitos hexadecimais.

    >>> crc16("123456789")
    '29B1'
    """
    crc = 0xFFFF
    for byte in dados.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


# ---------- Textos ----------


def _campo(id_: str, valor: str) -> str:
    if len(valor) > 99:
        raise ValueError(f"Campo {id_} passou de 99 caracteres")
    return f"{id_}{len(valor):02d}{valor}"


def limpar_texto(texto: str, limite: int) -> str:
    """Nome e cidade vão sem acento e em maiúsculas (muitos leitores de banco quebram com acento).

    >>> limpar_texto("São José dos Campos", 15)
    'SAO JOSE DOS CA'
    """
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9 .,\-/&]", "", sem_acento)
    return re.sub(r"\s+", " ", limpo).strip().upper()[:limite].rstrip()


def _valor(valor: str | float | Decimal | None) -> str | None:
    if valor is None or valor == "":
        return None
    try:
        texto = str(valor).strip().replace("R$", "").strip()
        if "," in texto:  # 1.234,56 (jeito brasileiro)
            texto = texto.replace(".", "").replace(",", ".")
        d = Decimal(texto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"Valor '{valor}' inválido. Exemplos: 10, 10.50, 1.234,56") from None
    if d <= 0:
        raise ValueError("O valor precisa ser maior que zero (para deixar em aberto, não informe valor).")
    if d >= Decimal("10000000000"):
        raise ValueError("Valor grande demais para um código Pix.")
    return f"{d:.2f}"


def _txid(txid: str | None) -> str:
    if not txid:
        return "***"
    if not re.fullmatch(r"[A-Za-z0-9]{1,25}", txid):
        raise ValueError("O identificador (txid) aceita só letras e números, sem espaço, até 25 caracteres.")
    return txid


# ---------- Gerar ----------


@dataclass
class Cobranca:
    """Tudo que vai num código Pix estático."""

    chave: Chave
    nome: str
    cidade: str
    valor: str | None = None
    txid: str = "***"
    descricao: str = ""

    @property
    def codigo(self) -> str:
        conta = _campo("00", GUI_PIX) + _campo("01", self.chave.valor)
        if self.descricao:
            conta += _campo("02", self.descricao)
        partes = [
            _campo("00", "01"),
            _campo("26", conta),
            _campo("52", "0000"),
            _campo("53", "986"),
        ]
        if self.valor:
            partes.append(_campo("54", self.valor))
        partes += [
            _campo("58", "BR"),
            _campo("59", self.nome),
            _campo("60", self.cidade),
            _campo("62", _campo("05", self.txid)),
            "6304",
        ]
        sem_crc = "".join(partes)
        return sem_crc + crc16(sem_crc)


def gerar(
    chave: str | Chave,
    nome: str,
    cidade: str,
    valor: str | float | Decimal | None = None,
    txid: str | None = None,
    descricao: str | None = None,
) -> Cobranca:
    """Monta uma cobrança Pix. Valida tudo e explica o que estiver errado.

    >>> c = gerar("ana@email.com", "Ana Souza", "São Luís", valor="25,90", txid="PEDIDO42")
    >>> c.codigo
    '00020126350014br.gov.bcb.pix0113ana@email.com520400005303986540525.905802BR5909ANA SOUZA6008SAO LUIS62120508PEDIDO4263049D9A'
    """
    chave_ok = chave if isinstance(chave, Chave) else normalizar_chave(chave)
    nome_ok = limpar_texto(nome, LIMITE_NOME)
    cidade_ok = limpar_texto(cidade, LIMITE_CIDADE)
    if not nome_ok:
        raise ValueError("Informe o nome de quem recebe.")
    if not cidade_ok:
        raise ValueError("Informe a cidade de quem recebe.")

    desc = limpar_texto(descricao or "", 99).capitalize() if descricao else ""
    espaco = LIMITE_CONTA - len(_campo("00", GUI_PIX)) - len(_campo("01", chave_ok.valor)) - 4
    if len(desc) > espaco:
        if espaco <= 0:
            desc = ""
        else:
            raise ValueError(f"Descrição longa demais para essa chave: cabem {espaco} caracteres.")
    return Cobranca(chave_ok, nome_ok, cidade_ok, _valor(valor), _txid(txid), desc)


# ---------- Ler ----------


@dataclass
class Campo:
    id: str
    nome: str
    valor: str
    filhos: list[Campo] = field(default_factory=list)


NOMES = {
    "00": "Versão do formato",
    "01": "Uso único",
    "26": "Conta Pix",
    "52": "Categoria do comércio",
    "53": "Moeda",
    "54": "Valor",
    "58": "País",
    "59": "Recebedor",
    "60": "Cidade",
    "62": "Dados adicionais",
    "63": "CRC16",
}
NOMES_CONTA = {"00": "Identificador", "01": "Chave", "02": "Descrição", "25": "URL (Pix dinâmico)"}
NOMES_ADICIONAIS = {"05": "Identificador (txid)"}


def _tlv(texto: str, onde: str = "") -> list[tuple[str, str, int]]:
    """Separa "ID TAMANHO VALOR" repetidos. Devolve (id, valor, posição)."""
    campos = []
    i = 0
    while i < len(texto):
        cabecalho = texto[i : i + 4]
        if len(cabecalho) < 4 or not cabecalho.isdigit():
            raise CodigoInvalido(f"Campo malformado{onde} na posição {i + 1}: esperava ID e tamanho (4 dígitos), achei '{cabecalho}'.")
        id_, tam = cabecalho[:2], int(cabecalho[2:])
        valor = texto[i + 4 : i + 4 + tam]
        if len(valor) < tam:
            raise CodigoInvalido(f"O campo {id_}{onde} diz ter {tam} caracteres, mas o código acaba antes. Ele foi cortado ao copiar?")
        campos.append((id_, valor, i))
        i += 4 + tam
    return campos


@dataclass
class Leitura:
    campos: list[Campo]
    chave: str | None
    nome: str | None
    cidade: str | None
    valor: str | None
    txid: str | None
    descricao: str | None
    url: str | None


def ler(codigo: str) -> Leitura:
    """Lê um código copia e cola, confere o CRC e devolve os campos com nomes legíveis."""
    codigo = codigo.strip()
    if not codigo:
        raise CodigoInvalido("O código está vazio.")
    if not codigo.startswith("000201"):
        raise CodigoInvalido("Isto não parece um código Pix: todo código Pix começa com 000201.")
    pos_crc = codigo.rfind("6304")
    if pos_crc == -1 or len(codigo) - pos_crc != 8:
        raise CodigoInvalido("Falta o CRC no final do código (campo 6304 + 4 caracteres). Ele foi cortado ao copiar?")

    esperado = crc16(codigo[: pos_crc + 4])
    encontrado = codigo[pos_crc + 4 :].upper()
    if esperado != encontrado:
        raise CodigoInvalido(
            f"CRC inválido: o código diz {encontrado}, mas o conteúdo dá {esperado}. "
            "Algum caractere foi alterado; não pague este código."
        )

    campos: list[Campo] = []
    dados: dict[str, str] = {}
    for id_, valor, _ in _tlv(codigo):
        campo = Campo(id_, NOMES.get(id_, f"Campo {id_}"), valor)
        if id_ == "26" or id_ == "62":
            nomes = NOMES_CONTA if id_ == "26" else NOMES_ADICIONAIS
            for sub_id, sub_valor, _ in _tlv(valor, f" dentro do {id_}"):
                campo.filhos.append(Campo(sub_id, nomes.get(sub_id, f"Subcampo {sub_id}"), sub_valor))
                dados[f"{id_}.{sub_id}"] = sub_valor
        campos.append(campo)
        dados[id_] = valor

    if dados.get("26.00", "").lower() != GUI_PIX:
        raise CodigoInvalido("O código não tem uma conta Pix (campo 26 com br.gov.bcb.pix).")
    chave = dados.get("26.01")
    if chave:
        try:
            normalizar_chave(chave)
        except ChaveInvalida as e:
            raise CodigoInvalido(f"A chave Pix do código é inválida: {e}") from None
    txid = dados.get("62.05")
    return Leitura(
        campos=campos,
        chave=chave,
        nome=dados.get("59"),
        cidade=dados.get("60"),
        valor=dados.get("54"),
        txid=None if txid in (None, "***") else txid,
        descricao=dados.get("26.02"),
        url=dados.get("26.25"),
    )
