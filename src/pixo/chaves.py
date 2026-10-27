"""Validação e normalização de chaves Pix.

Uma chave Pix pode ser CPF, CNPJ, telefone, e-mail ou chave aleatória (EVP, um UUID).
Antes de entrar no código, cada uma é conferida (dígitos verificadores, formato) e
escrita do jeito que o Banco Central espera: só dígitos, +55 no telefone, minúsculas...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class TipoChave(str, Enum):
    CPF = "cpf"
    CNPJ = "cnpj"
    TELEFONE = "telefone"
    EMAIL = "email"
    ALEATORIA = "aleatoria"


class ChaveInvalida(ValueError):
    """A chave não é válida. A mensagem explica o motivo em português."""


@dataclass(frozen=True)
class Chave:
    tipo: TipoChave
    valor: str  # como vai no código Pix

    def __str__(self) -> str:
        return self.valor

    @property
    def formatada(self) -> str:
        """Como uma pessoa escreveria: 123.456.789-09, (11) 98765-4321…"""
        v = self.valor
        if self.tipo is TipoChave.CPF:
            return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"
        if self.tipo is TipoChave.CNPJ:
            return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
        if self.tipo is TipoChave.TELEFONE:
            n = v[3:]
            meio = 5 if len(n) == 11 else 4
            return f"({n[:2]}) {n[2:2 + meio]}-{n[2 + meio:]}"
        return v


# ---------- Dígitos verificadores ----------


def _dv_cpf(base: str) -> str:
    def digito(parcial: str) -> int:
        peso = len(parcial) + 1
        soma = sum(int(d) * (peso - i) for i, d in enumerate(parcial))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = digito(base)
    return f"{d1}{digito(base + str(d1))}"


def cpf_valido(cpf: str) -> bool:
    cpf = re.sub(r"\D", "", cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:  # 111.111.111-11 passa na conta mas não existe
        return False
    return _dv_cpf(cpf[:9]) == cpf[9:]


def _dv_cnpj(base: str) -> str:
    # Desde 2026 o CNPJ pode ter letras nas 12 primeiras posições. A conta continua a
    # mesma: cada caractere vale (código ASCII - 48), então '0'-'9' valem 0-9 e 'A' vale 17.
    def digito(parcial: str) -> int:
        pesos = [*range(len(parcial) - 7, 1, -1), *range(9, 1, -1)]
        soma = sum((ord(c) - 48) * p for c, p in zip(parcial, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = digito(base)
    return f"{d1}{digito(base + str(d1))}"


def cnpj_valido(cnpj: str) -> bool:
    cnpj = re.sub(r"[.\-/\s]", "", cnpj).upper()
    if not re.fullmatch(r"[0-9A-Z]{12}\d{2}", cnpj) or cnpj == cnpj[0] * 14:
        return False
    return _dv_cnpj(cnpj[:12]) == cnpj[12:]


# ---------- Detecção e normalização ----------

_EMAIL = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def normalizar_chave(texto: str, tipo: TipoChave | str | None = None) -> Chave:
    """Descobre o tipo da chave (ou usa o informado), valida e devolve no formato do Pix.

    >>> normalizar_chave("123.456.789-09")
    Chave(tipo=<TipoChave.CPF: 'cpf'>, valor='12345678909')
    >>> normalizar_chave("(11) 98765-4321").valor
    '+5511987654321'
    """
    bruto = texto.strip()
    if not bruto:
        raise ChaveInvalida("A chave Pix está vazia.")
    if tipo is not None:
        tipo = TipoChave(tipo)
        return _validar(bruto, tipo)

    minusculo = bruto.lower()
    if "@" in bruto:
        return _validar(bruto, TipoChave.EMAIL)
    if _UUID.match(minusculo):
        return _validar(bruto, TipoChave.ALEATORIA)
    if bruto.startswith("+"):
        return _validar(bruto, TipoChave.TELEFONE)

    so_digitos = re.sub(r"\D", "", bruto)
    sem_pontuacao = re.sub(r"[.\-/\s]", "", bruto).upper()
    if re.fullmatch(r"[0-9A-Z]{12}\d{2}", sem_pontuacao) and not sem_pontuacao.isdigit():
        return _validar(bruto, TipoChave.CNPJ)  # CNPJ novo, com letras
    if len(so_digitos) == 14:
        return _validar(bruto, TipoChave.CNPJ)
    if len(so_digitos) == 11:
        # 11 dígitos pode ser CPF ou celular (DDD + 9 dígitos). Dígito verificador desempata.
        if cpf_valido(so_digitos):
            return Chave(TipoChave.CPF, so_digitos)
        if re.search(r"[()\s]", bruto) or so_digitos[2] == "9":
            return _validar(bruto, TipoChave.TELEFONE)
        raise ChaveInvalida(f"'{bruto}' parece um CPF, mas os dígitos verificadores não conferem.")
    if len(so_digitos) in (10, 12, 13):
        return _validar(bruto, TipoChave.TELEFONE)
    raise ChaveInvalida(
        f"Não reconheci '{bruto}' como chave Pix. Use CPF, CNPJ, telefone com DDD, e-mail ou chave aleatória."
    )


def _validar(bruto: str, tipo: TipoChave) -> Chave:
    if tipo is TipoChave.CPF:
        digitos = re.sub(r"\D", "", bruto)
        if len(digitos) != 11:
            raise ChaveInvalida(f"CPF precisa ter 11 dígitos, '{bruto}' tem {len(digitos)}.")
        if not cpf_valido(digitos):
            raise ChaveInvalida(f"CPF '{bruto}' inválido: os dígitos verificadores não conferem.")
        return Chave(tipo, digitos)

    if tipo is TipoChave.CNPJ:
        limpo = re.sub(r"[.\-/\s]", "", bruto).upper()
        if len(limpo) != 14:
            raise ChaveInvalida(f"CNPJ precisa ter 14 caracteres, '{bruto}' tem {len(limpo)}.")
        if not cnpj_valido(limpo):
            raise ChaveInvalida(f"CNPJ '{bruto}' inválido: os dígitos verificadores não conferem.")
        return Chave(tipo, limpo)

    if tipo is TipoChave.TELEFONE:
        digitos = re.sub(r"\D", "", bruto)
        if bruto.strip().startswith("+") and not digitos.startswith("55"):
            raise ChaveInvalida("O Pix só aceita telefones do Brasil (+55).")
        if not digitos.startswith("55") or len(digitos) in (10, 11):
            digitos = "55" + digitos
        nacional = digitos[2:]
        if len(nacional) not in (10, 11):
            raise ChaveInvalida(f"Telefone '{bruto}' precisa de DDD + número (10 ou 11 dígitos).")
        if nacional[0] == "0" or nacional[1] == "0":
            raise ChaveInvalida(f"DDD inválido em '{bruto}'.")
        return Chave(tipo, "+" + digitos)

    if tipo is TipoChave.EMAIL:
        email = bruto.lower()
        if len(email) > 77 or not _EMAIL.match(email):
            raise ChaveInvalida(f"E-mail '{bruto}' inválido.")
        return Chave(tipo, email)

    uuid = bruto.lower()
    if not _UUID.match(uuid):
        raise ChaveInvalida(
            f"Chave aleatória '{bruto}' inválida: deve ter o formato 123e4567-e89b-12d3-a456-426614174000."
        )
    return Chave(TipoChave.ALEATORIA, uuid)
