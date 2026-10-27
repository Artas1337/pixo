"""Desenhar o QR Code: no terminal, em SVG e em PNG (escrito à mão com zlib, sem Pillow)."""

from __future__ import annotations

import struct
import zlib

from .qrcode import QRCode

BORDA = 4  # a norma pede 4 módulos de margem clara em volta


def _grade(qr: QRCode, borda: int) -> list[list[bool]]:
    t = qr.tamanho + 2 * borda
    vazio = [False] * t
    return [vazio[:] for _ in range(borda)] + [
        [False] * borda + linha + [False] * borda for linha in qr.modulos
    ] + [vazio[:] for _ in range(borda)]


def terminal(qr: QRCode, cor: bool = True, borda: int = 2) -> str:
    """Duas linhas do QR por linha de texto, usando meio-bloco (▀ ▄ █).

    Com `cor`, força fundo branco e frente preta (funciona em terminal claro ou escuro).
    """
    g = _grade(qr, borda)
    if len(g) % 2:
        g.append([False] * len(g[0]))
    linhas = []
    for y in range(0, len(g), 2):
        cima, baixo = g[y], g[y + 1]
        if cor:
            chars = "".join(" ▄▀█"[(c << 1) | b] for c, b in zip(cima, baixo))
            linhas.append(f"\x1b[30;107m{chars}\x1b[0m")
        else:
            # Sem cor: desenha os módulos CLAROS (terminal escuro mostra o fundo como escuro).
            chars = "".join("█▀▄ "[(c << 1) | b] for c, b in zip(cima, baixo))
            linhas.append(chars)
    return "\n".join(linhas)


def svg(qr: QRCode, escala: int = 8, cor: str = "#000", fundo: str = "#fff") -> str:
    """SVG vetorial: imprime nítido em qualquer tamanho."""
    t = qr.tamanho + 2 * BORDA
    caminho = []
    for y, linha in enumerate(qr.modulos):
        x = 0
        while x < qr.tamanho:  # junta módulos escuros vizinhos num retângulo só
            if linha[x]:
                inicio = x
                while x < qr.tamanho and linha[x]:
                    x += 1
                caminho.append(f"M{inicio + BORDA},{y + BORDA}h{x - inicio}v1h-{x - inicio}z")
            x += 1
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {t} {t}" width="{t * escala}" height="{t * escala}" '
        f'shape-rendering="crispEdges"><rect width="100%" height="100%" fill="{fundo}"/>'
        f'<path d="{"".join(caminho)}" fill="{cor}"/></svg>'
    )


def png(qr: QRCode, escala: int = 10) -> bytes:
    """PNG preto e branco (1 bit por pixel), montado byte a byte."""
    g = _grade(qr, BORDA)
    lado = len(g) * escala
    bytes_por_linha = (lado + 7) // 8
    bruto = bytearray()
    for linha in g:
        bits = bytearray(bytes_por_linha)
        for x, escuro in enumerate(linha):
            if escuro:
                continue  # no PNG de 1 bit, 0 = preto e 1 = branco
            for dx in range(escala):
                px = x * escala + dx
                bits[px >> 3] |= 0x80 >> (px & 7)
        linha_png = b"\x00" + bytes(bits)  # filtro 0 (nenhum) no começo de cada linha
        bruto += linha_png * escala

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))

    cabecalho = struct.pack(">IIBBBBB", lado, lado, 1, 0, 0, 0, 0)  # 1 bit, tons de cinza
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", zlib.compress(bytes(bruto), 9)) + bloco(b"IEND", b"")
