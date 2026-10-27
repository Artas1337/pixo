import random
import string

import pytest
import zxingcpp

from pixo import Correcao, gerar, gerar_qr
from pixo.qrcode import TextoGrandeDemais, capacidade, penalidade
from pixo.render import png, svg, terminal

from .conftest import matriz_qr, png_para_matriz


def ler_qr(imagem):
    r = zxingcpp.read_barcodes(imagem)
    assert r, "o leitor não encontrou nenhum QR Code"
    return r[0]


@pytest.mark.parametrize("correcao", list(Correcao))
def test_qr_de_um_pix_e_lido_por_um_leitor_de_verdade(correcao):
    codigo = gerar("123.456.789-09", "Ana Souza", "São Luís", valor="25,90", txid="PEDIDO42").codigo
    qr = gerar_qr(codigo, correcao)
    assert ler_qr(matriz_qr(qr)).text == codigo


def test_textos_aleatorios_de_todos_os_tamanhos():
    """De 1 byte até perto da versão 40: inclui vários blocos e a informação de versão (v7+)."""
    rnd = random.Random(42)
    versoes = set()
    for tamanho in [1, 17, 50, 120, 300, 700, 1400, 2200]:
        texto = "".join(rnd.choice(string.ascii_letters + string.digits + " .,:/-") for _ in range(tamanho))
        qr = gerar_qr(texto, Correcao.L)
        versoes.add(qr.versao)
        assert ler_qr(matriz_qr(qr, escala=3)).text == texto
    assert min(versoes) == 1 and max(versoes) >= 35


@pytest.mark.parametrize("mascara", range(8))
def test_todas_as_mascaras_funcionam(mascara):
    texto = "Máscara de teste com acentuação ✓"
    qr = gerar_qr(texto, mascara=mascara)
    assert qr.mascara == mascara
    assert ler_qr(matriz_qr(qr)).text == texto


def test_escolhe_a_mascara_com_menor_penalidade():
    melhor = gerar_qr("Pix")
    pontos = {m: penalidade(gerar_qr("Pix", mascara=m).modulos) for m in range(8)}
    assert pontos[melhor.mascara] == min(pontos.values())


def test_escolhe_a_menor_versao_possivel():
    assert gerar_qr("a" * capacidade(1)).versao == 1
    assert gerar_qr("a" * (capacidade(1) + 1)).versao == 2


def test_texto_grande_demais():
    with pytest.raises(TextoGrandeDemais):
        gerar_qr("a" * 3000, Correcao.H)


def test_png_feito_a_mao_e_lido_pelo_leitor():
    codigo = gerar("ana@email.com", "Ana", "Recife", valor=10).codigo
    imagem = png_para_matriz(png(gerar_qr(codigo), escala=6))
    assert ler_qr(imagem).text == codigo


def test_svg_e_terminal():
    qr = gerar_qr("oi")
    s = svg(qr)
    assert s.startswith("<svg") and 'viewBox="0 0 29 29"' in s
    desenho = terminal(qr, cor=False)
    assert len(desenho.splitlines()) == (21 + 4 + 1) // 2
