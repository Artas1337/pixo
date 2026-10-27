"""Pixo: gere e confira cobranças Pix (copia e cola + QR Code) sem dependências."""

from .chaves import Chave, ChaveInvalida, TipoChave, cnpj_valido, cpf_valido, normalizar_chave
from .payload import Cobranca, CodigoInvalido, crc16, gerar, ler
from .qrcode import Correcao, QRCode, gerar_qr

__version__ = "1.0.0"

__all__ = [
    "Chave", "ChaveInvalida", "TipoChave", "cnpj_valido", "cpf_valido", "normalizar_chave",
    "Cobranca", "CodigoInvalido", "crc16", "gerar", "ler",
    "Correcao", "QRCode", "gerar_qr",
]
