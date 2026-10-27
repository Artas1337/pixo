import struct
import zlib

import numpy as np
import pytest


def png_para_matriz(dados: bytes) -> np.ndarray:
    """Lê de volta o PNG de 1 bit que o Pixo escreve (para o leitor de QR conferir)."""
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, largura = 8, b"", 0
    while pos < len(dados):
        tam = struct.unpack(">I", dados[pos : pos + 4])[0]
        tipo = dados[pos + 4 : pos + 8]
        corpo = dados[pos + 8 : pos + 8 + tam]
        assert zlib.crc32(tipo + corpo) == struct.unpack(">I", dados[pos + 8 + tam : pos + 12 + tam])[0]
        if tipo == b"IHDR":
            largura = struct.unpack(">I", corpo[:4])[0]
        elif tipo == b"IDAT":
            idat += corpo
        pos += 12 + tam
    bruto = zlib.decompress(idat)
    por_linha = 1 + (largura + 7) // 8
    linhas = [bruto[i + 1 : i + por_linha] for i in range(0, len(bruto), por_linha)]
    bits = np.unpackbits(np.frombuffer(b"".join(linhas), np.uint8)).reshape(len(linhas), -1)[:, :largura]
    return (bits * 255).astype(np.uint8)


def matriz_qr(qr, escala: int = 4, borda: int = 4) -> np.ndarray:
    t = qr.tamanho + 2 * borda
    a = np.full((t, t), 255, np.uint8)
    for y, linha in enumerate(qr.modulos):
        for x, escuro in enumerate(linha):
            if escuro:
                a[y + borda, x + borda] = 0
    return np.kron(a, np.ones((escala, escala), np.uint8))


@pytest.fixture
def config_vazia(tmp_path, monkeypatch):
    arquivo = tmp_path / "pixo.json"
    monkeypatch.setenv("PIXO_CONFIG", str(arquivo))
    monkeypatch.setenv("NO_COLOR", "1")
    return arquivo
