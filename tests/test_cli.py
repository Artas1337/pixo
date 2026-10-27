import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import zxingcpp

from pixo.cli import main
from pixo.web import _Handler

from .conftest import png_para_matriz


def _codigo(saida: str) -> str:
    return next(linha for linha in saida.splitlines() if linha.startswith("000201"))


def test_gerar_com_tudo_na_linha(config_vazia, capsys, tmp_path):
    destino = tmp_path / "pix.png"
    rc = main(["gerar", "25,90", "--chave", "ana@email.com", "--nome", "Ana", "--cidade", "Recife", "--png", str(destino), "--sem-qr"])
    saida = capsys.readouterr().out
    assert rc == 0
    assert "R$ 25,90 para ANA (RECIFE)" in saida
    assert zxingcpp.read_barcodes(png_para_matriz(destino.read_bytes()))[0].text == _codigo(saida)


def test_config_evita_repetir_dados(config_vazia, capsys):
    assert main(["config", "--chave", "(11) 98765-4321", "--nome", "Bia", "--cidade", "Santos"]) == 0
    assert json.loads(config_vazia.read_text(encoding="utf-8"))["chave"] == "+5511987654321"
    assert main(["gerar", "10", "--sem-qr"]) == 0
    assert "R$ 10,00 para BIA (SANTOS)" in capsys.readouterr().out


def test_gerar_sem_recebedor_explica(config_vazia, capsys):
    assert main(["gerar", "10"]) == 2
    assert "pixo config" in capsys.readouterr().err


def test_ler_valido_e_adulterado(config_vazia, capsys):
    main(["gerar", "7", "--chave", "ana@email.com", "--nome", "Ana", "--cidade", "Recife", "--sem-qr"])
    codigo = _codigo(capsys.readouterr().out)
    assert main(["ler", codigo]) == 0
    assert "Você vai pagar R$ 7,00 para ANA" in capsys.readouterr().out
    assert main(["ler", codigo[:-1] + ("0" if codigo[-1] != "0" else "1")]) == 1
    assert "CRC inválido" in capsys.readouterr().err


def test_lote_gera_arquivos_e_aponta_linhas_com_erro(config_vazia, tmp_path, capsys):
    planilha = tmp_path / "itens.csv"
    planilha.write_text("titulo;valor;txid\nBolo;12,00;BOLO1\nErrado;abc;X\nLivre;;\n", encoding="utf-8")
    saida = tmp_path / "out"
    rc = main(["lote", str(planilha), "-o", str(saida), "--chave", "ana@email.com", "--nome", "Ana", "--cidade", "Recife"])
    assert rc == 1  # gerou, mas avisa que uma linha falhou
    assert "linha 3" in capsys.readouterr().err
    assert sorted(p.name for p in saida.glob("*.png")) == ["001-bolo.png", "002-livre.png"]
    assert "R$ 12,00" in (saida / "index.html").read_text(encoding="utf-8")


def test_pagina_web_local():
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    try:
        q = "chave=ana%40email.com&nome=Ana&cidade=Recife&valor=10"
        pagina = urllib.request.urlopen(f"{base}/?{q}").read().decode()
        assert "<svg" in pagina and "R$ 10,00" in pagina
        imagem = urllib.request.urlopen(f"{base}/qr.png?{q}").read()
        assert zxingcpp.read_barcodes(png_para_matriz(imagem))[0].text.startswith("000201")
        erro = urllib.request.urlopen(f"{base}/?chave=123&nome=A&cidade=B").read().decode()
        assert 'class="erro"' in erro
    finally:
        servidor.shutdown()
