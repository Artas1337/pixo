import pytest

from pixo import CodigoInvalido, crc16, gerar, ler

# Exemplo do Manual de Padrões para Iniciação do Pix (Banco Central)
EXEMPLO_BCB = (
    "00020126580014br.gov.bcb.pix0136123e4567-e12b-12d1-a456-426655440000"
    "5204000053039865802BR5913Fulano de Tal6008BRASILIA62070503***63041D3D"
)


def test_crc16_confere_com_o_exemplo_do_banco_central():
    assert crc16(EXEMPLO_BCB[:-4]) == "1D3D"
    assert crc16("123456789") == "29B1"  # valor de referência do CRC-16/CCITT-FALSE


def test_le_o_exemplo_do_banco_central():
    r = ler(EXEMPLO_BCB)
    assert (r.chave, r.nome, r.cidade, r.valor, r.txid) == (
        "123e4567-e12b-12d1-a456-426655440000",
        "Fulano de Tal",
        "BRASILIA",
        None,
        None,
    )


def test_gera_codigo_completo():
    c = gerar("123.456.789-09", "Ana Souza", "São Luís", valor="1.234,5", txid="PEDIDO42", descricao="Bolo de pote")
    assert c.codigo.startswith("000201")
    assert "0014br.gov.bcb.pix" in c.codigo
    assert "54071234.50" in c.codigo  # valor com ponto e 2 casas
    assert "5909ANA SOUZA" in c.codigo and "6008SAO LUIS" in c.codigo
    assert "0508PEDIDO42" in c.codigo
    assert c.codigo[-4:] == crc16(c.codigo[:-4])


def test_ida_e_volta():
    c = gerar("+55 11 98765-4321", "José da Silva Pereira Sobrinho Neto", "São José dos Campos", valor=9.9)
    r = ler(c.codigo)
    assert r.chave == "+5511987654321"
    assert r.nome == "JOSE DA SILVA PEREIRA SOB"  # cortado em 25
    assert r.cidade == "SAO JOSE DOS CA"  # cortado em 15
    assert r.valor == "9.90"


@pytest.mark.parametrize(
    "valor, esperado",
    [("10", "10.00"), ("10,5", "10.50"), ("R$ 1.000,00", "1000.00"), (0.1 + 0.2, "0.30"), ("2.675", "2.68")],
)
def test_valores(valor, esperado):
    assert gerar("ana@email.com", "Ana", "SP", valor=valor).valor == esperado


@pytest.mark.parametrize("valor", ["0", "-5", "dez reais"])
def test_valor_invalido(valor):
    with pytest.raises(ValueError):
        gerar("ana@email.com", "Ana", "SP", valor=valor)


def test_txid_e_descricao():
    with pytest.raises(ValueError, match="letras e números"):
        gerar("ana@email.com", "Ana", "SP", txid="pedido 42")
    with pytest.raises(ValueError, match="Descrição longa demais"):
        gerar("123e4567-e12b-12d1-a456-426655440000", "Ana", "SP", descricao="x" * 60)


def test_detecta_codigo_adulterado():
    c = gerar("ana@email.com", "Ana", "SP", valor="10").codigo
    adulterado = c.replace("540510.00", "540590.00")
    with pytest.raises(CodigoInvalido, match="CRC inválido.*não pague"):
        ler(adulterado)


@pytest.mark.parametrize(
    "codigo, trecho",
    [
        ("", "vazio"),
        ("https://exemplo.com", "não parece um código Pix"),
        (EXEMPLO_BCB[:-30], "Falta o CRC"),
    ],
)
def test_codigos_quebrados(codigo, trecho):
    with pytest.raises(CodigoInvalido, match=trecho):
        ler(codigo)
