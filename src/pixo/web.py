"""Uma página local para quem não quer usar o terminal: `pixo web` abre no navegador.

Usa só o servidor HTTP da biblioteca padrão. Escuta apenas em 127.0.0.1: nada sai do
seu computador.
"""

from __future__ import annotations

import html
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import render
from .chaves import ChaveInvalida
from .payload import CodigoInvalido, gerar, ler
from .qrcode import gerar_qr

ESTILO = """
:root { color-scheme: light dark; --a: #00b4a0; }
body { font-family: system-ui, sans-serif; max-width: 880px; margin: 0 auto; padding: 24px 16px; }
h1 { margin: 0 0 4px; } h1 span { color: var(--a); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }
form { display: grid; gap: 10px; }
label { display: grid; gap: 4px; font-size: 14px; font-weight: 600; }
input, textarea { font: inherit; padding: 9px 11px; border: 1px solid #8886; border-radius: 9px; background: transparent; }
button { font: inherit; font-weight: 700; padding: 10px 16px; border: 0; border-radius: 9px; background: var(--a); color: #fff; cursor: pointer; }
.qr { background: #fff; border-radius: 14px; padding: 8px; } .qr svg { width: 100%; height: auto; display: block; }
code { display: block; word-break: break-all; font-size: 12px; padding: 10px; border-radius: 9px; background: #8881; }
.erro { padding: 10px 12px; border-radius: 9px; background: #e5484d22; color: #e5484d; }
.campos div { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid #8883; font-size: 14px; }
small { opacity: .7; } hr { border: 0; border-top: 1px solid #8883; margin: 28px 0; }
@media (max-width: 680px) { .grid { grid-template-columns: 1fr; } }
"""


def _pagina(form: dict[str, str], resultado: str = "", leitura: str = "") -> str:
    v = lambda k: html.escape(form.get(k, ""), quote=True)  # noqa: E731
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pixo</title><style>{ESTILO}</style></head><body>
<h1><span>Pixo</span> · cobranças Pix</h1><p><small>Tudo é gerado no seu computador. Nenhum dado é enviado.</small></p>
<div class="grid">
<form method="get" action="/">
  <label>Chave Pix <input name="chave" value="{v('chave')}" required placeholder="CPF, CNPJ, telefone, e-mail ou aleatória"></label>
  <label>Nome de quem recebe <input name="nome" value="{v('nome')}" required maxlength="60"></label>
  <label>Cidade <input name="cidade" value="{v('cidade')}" required maxlength="60"></label>
  <label>Valor (opcional) <input name="valor" value="{v('valor')}" placeholder="25,90"></label>
  <label>Identificador (opcional) <input name="txid" value="{v('txid')}" placeholder="PEDIDO42" maxlength="25"></label>
  <label>Descrição (opcional) <input name="descricao" value="{v('descricao')}" placeholder="Bolo de pote"></label>
  <button>Gerar QR Code</button>
</form>
<div>{resultado or '<p><small>Preencha ao lado para gerar o QR Code.</small></p>'}</div>
</div>
<hr>
<form method="get" action="/ler"><label>Conferir um código Pix copia e cola
<textarea name="codigo" rows="3" required>{v('codigo')}</textarea></label><button>Conferir</button></form>
{leitura}
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (nome exigido pelo http.server)
        url = urlparse(self.path)
        form = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            self._html(_pagina(form, self._gerar(form) if form.get("chave") else ""))
        elif url.path == "/ler":
            self._html(_pagina(form, leitura=self._ler(form.get("codigo", ""))))
        elif url.path == "/qr.png":
            try:
                c = gerar(form.get("chave", ""), form.get("nome", ""), form.get("cidade", ""), form.get("valor") or None, form.get("txid") or None, form.get("descricao") or None)
            except (ValueError, ChaveInvalida) as e:
                self.send_error(400, str(e))
                return
            corpo = render.png(gerar_qr(c.codigo))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", 'attachment; filename="pix.png"')
            self.end_headers()
            self.wfile.write(corpo)
        else:
            self.send_error(404)

    def _gerar(self, form: dict[str, str]) -> str:
        try:
            c = gerar(form.get("chave", ""), form.get("nome", ""), form.get("cidade", ""), form.get("valor") or None, form.get("txid") or None, form.get("descricao") or None)
        except (ValueError, ChaveInvalida) as e:
            return f'<p class="erro">{html.escape(str(e))}</p>'
        svg = render.svg(gerar_qr(c.codigo))
        valor = f"R$ {c.valor.replace('.', ',')}" if c.valor else "valor livre (quem paga digita)"
        return (
            f'<div class="qr">{svg}</div><p><strong>{valor}</strong> para {html.escape(c.nome)}</p>'
            f'<code id="c">{html.escape(c.codigo)}</code>'
            f'<p><button onclick="navigator.clipboard.writeText(document.getElementById(\'c\').textContent);this.textContent=\'Copiado ✓\'">Copiar código</button> '
            f'<a href="/qr.png?{urlparse(self.path).query}">Baixar PNG</a></p>'
        )

    def _ler(self, codigo: str) -> str:
        try:
            r = ler(codigo)
        except CodigoInvalido as e:
            return f'<p class="erro">✗ {html.escape(str(e))}</p>'
        linhas = [("Recebedor", r.nome), ("Cidade", r.cidade), ("Chave", r.chave), ("Valor", f"R$ {r.valor.replace('.', ',')}" if r.valor else "livre"), ("Identificador", r.txid), ("Descrição", r.descricao)]
        itens = "".join(f"<div><span>{k}</span><strong>{html.escape(v)}</strong></div>" for k, v in linhas if v)
        return f'<p>✓ Código válido (CRC confere).</p><div class="campos">{itens}</div>'

    def _html(self, corpo: str) -> None:
        dados = corpo.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *args: object) -> None:  # silencia o log padrão
        pass


def servir(porta: int = 8765, abrir: bool = True) -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), _Handler)
    url = f"http://127.0.0.1:{servidor.server_address[1]}/"
    print(f"Pixo rodando em {url}  (Ctrl+C para sair)")
    if abrir:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nAté mais!")
    finally:
        servidor.server_close()
