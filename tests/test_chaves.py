import pytest

from pixo import ChaveInvalida, TipoChave, cnpj_valido, cpf_valido, normalizar_chave


@pytest.mark.parametrize(
    "entrada, tipo, valor",
    [
        ("123.456.789-09", TipoChave.CPF, "12345678909"),
        ("11.222.333/0001-81", TipoChave.CNPJ, "11222333000181"),
        ("12.ABC.345/01DE-35", TipoChave.CNPJ, "12ABC34501DE35"),  # CNPJ alfanumérico (exemplo oficial da Receita)
        ("(11) 98765-4321", TipoChave.TELEFONE, "+5511987654321"),
        ("+55 98 98888-7777", TipoChave.TELEFONE, "+5598988887777"),
        ("11 3333-4444", TipoChave.TELEFONE, "+551133334444"),
        ("55987654321", TipoChave.TELEFONE, "+5555987654321"),  # DDD 55 (RS), sem o +55
        ("Ana.Souza@Email.com", TipoChave.EMAIL, "ana.souza@email.com"),
        ("123E4567-E89B-12D3-A456-426614174000", TipoChave.ALEATORIA, "123e4567-e89b-12d3-a456-426614174000"),
    ],
)
def test_detecta_e_normaliza(entrada, tipo, valor):
    chave = normalizar_chave(entrada)
    assert (chave.tipo, chave.valor) == (tipo, valor)


def test_formata_para_humanos():
    assert normalizar_chave("12345678909").formatada == "123.456.789-09"
    assert normalizar_chave("11222333000181").formatada == "11.222.333/0001-81"
    assert normalizar_chave("+5511987654321").formatada == "(11) 98765-4321"


def test_digitos_verificadores():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("529.982.247-26")
    assert not cpf_valido("111.111.111-11")  # passa na conta, mas não existe
    assert cnpj_valido("11.222.333/0001-81")
    assert not cnpj_valido("11.222.333/0001-82")
    assert not cnpj_valido("12.ABC.345/01DE-36")


@pytest.mark.parametrize(
    "entrada, trecho",
    [
        ("", "vazia"),
        ("123.456.789-00", "dígitos verificadores"),
        ("11.222.333/0001-00", "dígitos verificadores"),
        ("ana@", "E-mail"),
        ("+1 202 555 0100", "Brasil"),
        ("abc", "Não reconheci"),
    ],
)
def test_explica_o_erro(entrada, trecho):
    with pytest.raises(ChaveInvalida, match=trecho):
        normalizar_chave(entrada)


def test_tipo_forcado():
    assert normalizar_chave("11987654321", tipo="telefone").valor == "+5511987654321"
    with pytest.raises(ChaveInvalida):
        normalizar_chave("11987654321", tipo="cpf")
