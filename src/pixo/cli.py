"""Linha de comando: `pixo gerar`, `pixo ler`, `pixo lote`, `pixo web`, `pixo config`."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, render
from .chaves import ChaveInvalida, normalizar_chave
from .lote import ler_planilha, salvar
from .payload import CodigoInvalido, gerar, ler
from .qrcode import Correcao, gerar_qr

# ---------- Cores (só quando a saída é um terminal) ----------


def _usa_cor() -> bool:
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _c(texto: str, codigo: str) -> str:
    return f"\x1b[{codigo}m{texto}\x1b[0m" if _usa_cor() else texto


verde = lambda t: _c(t, "32")  # noqa: E731
vermelho = lambda t: _c(t, "31")  # noqa: E731
negrito = lambda t: _c(t, "1")  # noqa: E731
fraco = lambda t: _c(t, "2")  # noqa: E731


# ---------- Configuração (para não digitar chave, nome e cidade toda vez) ----------


def _arquivo_config() -> Path:
    return Path(os.environ.get("PIXO_CONFIG", Path.home() / ".pixo.json"))


def _carregar_config() -> dict[str, str]:
    try:
        return json.loads(_arquivo_config().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _recebedor(args: argparse.Namespace) -> tuple[str, str, str]:
    cfg = _carregar_config()
    chave = args.chave or cfg.get("chave")
    nome = args.nome or cfg.get("nome")
    cidade = args.cidade or cfg.get("cidade")
    faltando = [n for n, v in (("--chave", chave), ("--nome", nome), ("--cidade", cidade)) if not v]
    if faltando:
        raise ValueError(
            f"Faltou {', '.join(faltando)}. Informe na hora ou salve uma vez com:\n"
            '  pixo config --chave SUA_CHAVE --nome "Seu Nome" --cidade "Sua Cidade"'
        )
    return chave, nome, cidade  # type: ignore[return-value]


def _copiar(texto: str) -> bool:
    """Copia para a área de transferência com a ferramenta do sistema (sem dependências)."""
    for cmd in (["clip"], ["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=texto.encode("utf-16le" if cmd[0] == "clip" else "utf-8"), check=True)
                return True
            except (OSError, subprocess.CalledProcessError):
                continue
    return False


# ---------- Comandos ----------


def cmd_gerar(args: argparse.Namespace) -> int:
    chave, nome, cidade = _recebedor(args)
    c = gerar(chave, nome, cidade, valor=args.valor, txid=args.txid, descricao=args.descricao)
    qr = gerar_qr(c.codigo, Correcao[args.correcao])

    if not args.sem_qr:
        print(render.terminal(qr, cor=not args.sem_cor))
        print()
    valor = f"R$ {c.valor.replace('.', ',')}" if c.valor else "valor livre (quem paga digita)"
    print(f"{negrito(valor)} para {c.nome} ({c.cidade}) · chave {c.chave.formatada} ({c.chave.tipo.value})")
    if c.txid != "***":
        print(fraco(f"identificador: {c.txid}"))
    print()
    print(fraco("Pix copia e cola:"))
    print(c.codigo)

    if args.png:
        Path(args.png).write_bytes(render.png(qr))
        print(verde(f"✓ PNG salvo em {args.png}"))
    if args.svg:
        Path(args.svg).write_text(render.svg(qr), encoding="utf-8")
        print(verde(f"✓ SVG salvo em {args.svg}"))
    if args.copiar:
        print(verde("✓ código copiado") if _copiar(c.codigo) else vermelho("não consegui copiar automaticamente"))
    return 0


def cmd_ler(args: argparse.Namespace) -> int:
    codigo = sys.stdin.read() if args.codigo == "-" else args.codigo
    try:
        r = ler(codigo)
    except CodigoInvalido as e:
        print(vermelho(f"✗ {e}"), file=sys.stderr)
        return 1
    print(verde("✓ Código Pix válido (CRC confere)"))
    print()
    for campo in r.campos:
        print(f"  {fraco(campo.id)}  {campo.nome:<22} {'' if campo.filhos else campo.valor}")
        for f in campo.filhos:
            print(f"      {fraco(f.id)}  {f.nome:<18} {f.valor}")
    print()
    quem = f"{negrito(r.nome or '?')} ({r.cidade})"
    if r.valor:
        print(f"Você vai pagar {negrito('R$ ' + r.valor.replace('.', ','))} para {quem}.")
    else:
        print(f"Pagamento para {quem}. O valor é livre: você digita na hora de pagar.")
    return 0


def cmd_lote(args: argparse.Namespace) -> int:
    chave, nome, cidade = _recebedor(args)
    texto = Path(args.planilha).read_text(encoding="utf-8-sig")
    itens, erros = ler_planilha(texto, normalizar_chave(chave), nome, cidade)
    for e in erros:
        print(vermelho(f"✗ linha {e.linha}: {e.mensagem}"), file=sys.stderr)
    if not itens:
        print(vermelho("Nenhuma cobrança gerada."), file=sys.stderr)
        return 1
    indice = salvar(itens, Path(args.saida))
    print(verde(f"✓ {len(itens)} cobranças geradas em {args.saida}"))
    print(f"  Abra {indice} para ver e imprimir todas.")
    return 1 if erros else 0


def cmd_config(args: argparse.Namespace) -> int:
    cfg = _carregar_config()
    if args.chave:
        cfg["chave"] = normalizar_chave(args.chave).valor
    if args.nome:
        cfg["nome"] = args.nome
    if args.cidade:
        cfg["cidade"] = args.cidade
    if args.chave or args.nome or args.cidade:
        _arquivo_config().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(verde(f"✓ salvo em {_arquivo_config()}"))
    if not cfg:
        print("Nada configurado ainda.")
    for k, v in cfg.items():
        print(f"  {k}: {v}")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from .web import servir

    servir(args.porta, abrir=not args.nao_abrir)
    return 0


# ---------- Argumentos ----------


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pixo", description="Gere e confira cobranças Pix (copia e cola + QR Code), offline.")
    p.add_argument("--versao", action="version", version=f"pixo {__version__}")
    sub = p.add_subparsers(dest="comando", required=True, metavar="comando")

    def recebedor(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--chave", help="chave Pix (CPF, CNPJ, telefone, e-mail ou aleatória)")
        sp.add_argument("--nome", help="nome de quem recebe")
        sp.add_argument("--cidade", help="cidade de quem recebe")

    g = sub.add_parser("gerar", help="gera uma cobrança", description="Gera o QR Code e o copia e cola.")
    g.add_argument("valor", nargs="?", help="ex.: 25,90 (sem valor, quem paga digita)")
    recebedor(g)
    g.add_argument("--txid", help="identificador da cobrança (letras e números)")
    g.add_argument("--descricao", help="texto que aparece para quem paga")
    g.add_argument("--png", metavar="ARQUIVO", help="salva o QR em PNG")
    g.add_argument("--svg", metavar="ARQUIVO", help="salva o QR em SVG")
    g.add_argument("--copiar", action="store_true", help="copia o código para a área de transferência")
    g.add_argument("--sem-qr", action="store_true", help="não desenha o QR no terminal")
    g.add_argument("--sem-cor", action="store_true", help="QR sem cores ANSI")
    g.add_argument("--correcao", choices="LMQH", default="M", help="nível de correção de erros (padrão: M)")
    g.set_defaults(fn=cmd_gerar)

    l_ = sub.add_parser("ler", help="confere um código copia e cola", description="Confere o CRC e mostra cada campo.")
    l_.add_argument("codigo", help='o código (ou "-" para ler da entrada padrão)')
    l_.set_defaults(fn=cmd_ler)

    lt = sub.add_parser("lote", help="gera várias cobranças de uma planilha CSV")
    lt.add_argument("planilha", help="CSV com as colunas: titulo, valor, txid, descricao")
    lt.add_argument("-o", "--saida", default="cobrancas", help="pasta de saída (padrão: cobrancas)")
    recebedor(lt)
    lt.set_defaults(fn=cmd_lote)

    cf = sub.add_parser("config", help="salva chave, nome e cidade para não digitar sempre")
    recebedor(cf)
    cf.set_defaults(fn=cmd_config)

    w = sub.add_parser("web", help="abre uma página no navegador para gerar e conferir")
    w.add_argument("--porta", type=int, default=8765)
    w.add_argument("--nao-abrir", action="store_true", help="não abre o navegador")
    w.set_defaults(fn=cmd_web)
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if os.name == "nt":
        os.system("")  # liga as cores ANSI no terminal do Windows
    args = _parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, ChaveInvalida) as e:
        print(vermelho(f"✗ {e}"), file=sys.stderr)
        return 2
    except OSError as e:
        print(vermelho(f"✗ {e}"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
