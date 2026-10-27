"""Gerar muitas cobranças de uma vez a partir de uma planilha (CSV).

Útil para quem vende: um QR por produto, por cliente ou por mensalidade. Gera um PNG
e um SVG de cada linha, mais uma página HTML pronta para imprimir com todos.
"""

from __future__ import annotations

import csv
import html
import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import render
from .chaves import Chave
from .payload import Cobranca, gerar
from .qrcode import gerar_qr

COLUNAS = {"valor", "txid", "descricao", "titulo"}


@dataclass
class Item:
    linha: int
    titulo: str
    cobranca: Cobranca


@dataclass
class ErroLinha:
    linha: int
    mensagem: str


def ler_planilha(texto: str, chave: Chave, nome: str, cidade: str) -> tuple[list[Item], list[ErroLinha]]:
    """Lê o CSV (separado por ';' como o Excel brasileiro salva, ou por ',')."""
    texto = texto.lstrip("﻿")
    primeira = texto.splitlines()[0] if texto.strip() else ""
    separador = ";" if primeira.count(";") >= primeira.count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=separador)
    if not leitor.fieldnames:
        return [], [ErroLinha(1, "Planilha vazia.")]
    cabecalho = {c.strip().lower() for c in leitor.fieldnames if c}
    desconhecidas = cabecalho - COLUNAS
    if desconhecidas:
        return [], [ErroLinha(1, f"Colunas desconhecidas: {', '.join(sorted(desconhecidas))}. Use: {', '.join(sorted(COLUNAS))}.")]

    itens, erros = [], []
    for n, linha in enumerate(leitor, start=2):
        campos = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
        if not any(campos.values()):
            continue
        try:
            c = gerar(chave, nome, cidade, valor=campos.get("valor") or None, txid=campos.get("txid") or None, descricao=campos.get("descricao") or None)
        except ValueError as e:
            erros.append(ErroLinha(n, str(e)))
            continue
        titulo = campos.get("titulo") or campos.get("descricao") or campos.get("txid") or f"Cobrança {n - 1}"
        itens.append(Item(n, titulo, c))
    return itens, erros


def _nome_arquivo(i: int, titulo: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")[:40] or "cobranca"
    return f"{i:03d}-{base}"


def salvar(itens: list[Item], pasta: Path) -> Path:
    """Escreve PNG + SVG de cada item e uma página `index.html` para imprimir."""
    pasta.mkdir(parents=True, exist_ok=True)
    cartoes = []
    for i, item in enumerate(itens, start=1):
        qr = gerar_qr(item.cobranca.codigo)
        nome = _nome_arquivo(i, item.titulo)
        (pasta / f"{nome}.png").write_bytes(render.png(qr))
        svg = render.svg(qr, escala=4)
        (pasta / f"{nome}.svg").write_text(svg, encoding="utf-8")
        valor = f"R$ {item.cobranca.valor.replace('.', ',')}" if item.cobranca.valor else "Valor livre"
        cartoes.append(
            f'<article><h2>{html.escape(item.titulo)}</h2><div class="qr">{svg}</div>'
            f'<p class="valor">{valor}</p><p class="codigo">{html.escape(item.cobranca.codigo)}</p></article>'
        )
    recebedor = html.escape(itens[0].cobranca.nome) if itens else ""
    pagina = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Cobranças Pix</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 24px; color: #111; }}
header {{ margin-bottom: 16px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }}
article {{ border: 1px solid #ddd; border-radius: 12px; padding: 14px; text-align: center; break-inside: avoid; }}
h2 {{ font-size: 15px; margin: 0 0 8px; }}
.qr svg {{ width: 100%; height: auto; }}
.valor {{ font-size: 20px; font-weight: 700; margin: 6px 0; }}
.codigo {{ font: 9px monospace; word-break: break-all; color: #555; }}
@media print {{ body {{ margin: 0; }} button {{ display: none; }} }}
</style></head><body>
<header><strong>Pix para {recebedor}</strong> · {len(itens)} cobranças · <button onclick="print()">Imprimir</button></header>
<main>{"".join(cartoes)}</main>
</body></html>"""
    indice = pasta / "index.html"
    indice.write_text(pagina, encoding="utf-8")
    return indice
