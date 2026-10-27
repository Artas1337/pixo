# Pixo: cobranças Pix no terminal, sem dependências

Gere o **QR Code e o "copia e cola" do Pix** com valor, identificador e descrição, e **confira um código Pix antes de pagar**. Tudo offline, em Python puro, **sem nenhuma dependência**: até o gerador de QR Code e o PNG foram escritos do zero.

![CI](https://github.com/Artas1337/pixo/actions/workflows/ci.yml/badge.svg)

> Projeto de portfólio feito para resolver um problema real: quem vende bolo, faz freela ou cobra mensalidade precisa gerar Pix com valor sem depender de app de banco nem mandar dados para site nenhum.

```
$ pixo gerar 25,90 --descricao "Bolo de pote"

  (o QR Code aparece aqui, desenhado no terminal)

R$ 25,90 para DOCERIA DA ANA (SAO LUIS) · chave 11.222.333/0001-81 (cnpj)

Pix copia e cola:
00020126520014br.gov.bcb.pix0114112223330001810212Bolo de pote52040000530398654...
```

## O que ele faz

| Comando | Para quê |
|---|---|
| `pixo gerar 25,90` | QR no terminal + copia e cola. `--png`, `--svg` salvam imagem; `--copiar` joga na área de transferência |
| `pixo ler "000201…"` | Confere um código antes de pagar: CRC, chave e cada campo com nome em português |
| `pixo lote planilha.csv` | Um QR por linha da planilha (produtos, clientes, mensalidades) + uma página pronta para **imprimir** |
| `pixo web` | Abre uma página no navegador para quem não quer usar o terminal (só em 127.0.0.1: nada sai do computador) |
| `pixo config` | Guarda chave, nome e cidade uma vez só |

**Conferindo um código adulterado** (alguém trocou R$ 10,00 por R$ 90,00):

```
$ pixo ler "00020126350014br.gov.bcb.pix0113ana@email.com520400005303986540590.005802BR5903ANA6006RECIFE62070503***63042418"
✗ CRC inválido: o código diz 2418, mas o conteúdo dá 402B. Algum caractere foi alterado; não pague este código.
```

## Instalação

Requer Python 3.10+.

```bash
pip install git+https://github.com/Artas1337/pixo
pixo config --chave "11.222.333/0001-81" --nome "Doceria da Ana" --cidade "São Luís"
pixo gerar 12,00 --txid BOLO01
```

Também funciona como biblioteca:

```python
from pixo import gerar, ler, gerar_qr
from pixo.render import png

cobranca = gerar("ana@email.com", "Ana Souza", "Recife", valor="25,90", txid="PEDIDO42")
print(cobranca.codigo)                                     # copia e cola
open("pix.png", "wb").write(png(gerar_qr(cobranca.codigo)))  # QR Code
print(ler(cobranca.codigo).valor)                          # "25.90"
```

## Como funciona por dentro

### 1. O código Pix (BR Code)

O "copia e cola" segue o padrão EMV de pagamentos: campos no formato **ID + tamanho + valor**, alguns com subcampos dentro. O último campo é um **CRC16** de tudo que vem antes: se um caractere mudar, o banco recusa. O Pixo monta e lê esse formato à mão ([payload.py](src/pixo/payload.py)), e o CRC é conferido contra o exemplo oficial do Manual do Banco Central.

### 2. As chaves Pix

Antes de entrar no código, a chave é **validada e normalizada** ([chaves.py](src/pixo/chaves.py)):

- **CPF e CNPJ** com dígitos verificadores, incluindo o **CNPJ alfanumérico** (com letras) que a Receita começou a emitir em 2026
- **Telefone** vira `+55DDDNUMERO`; 11 dígitos podem ser CPF ou celular, e o dígito verificador desempata
- **E-mail** em minúsculas; **chave aleatória** no formato UUID

### 3. O QR Code, do zero

[qrcode.py](src/pixo/qrcode.py) implementa a norma ISO/IEC 18004:

1. escolhe a menor **versão** (21×21 até 177×177) em que o texto cabe
2. codifica os bytes e completa com o preenchimento da norma
3. divide em blocos e calcula a **correção de erros Reed-Solomon** sobre o corpo finito GF(256), que é o que deixa o QR ser lido mesmo amassado
4. desenha os padrões fixos (quadrados dos cantos, alinhamento, linhas de tempo, informação de formato e versão) e preenche os dados em zigue-zague
5. testa as **8 máscaras** e escolhe a de menor penalidade (menos blocos grandes da mesma cor)

O PNG também é escrito à mão ([render.py](src/pixo/render.py)): cabeçalho, compressão com `zlib` e CRC32 de cada bloco.

## Decisões técnicas

| Problema | Solução |
|---|---|
| Como provar que um QR feito do zero funciona? | Os testes geram QR Codes e um **leitor de verdade** (ZXing, o mesmo usado em apps de celular) lê as imagens: todos os níveis de correção, as 8 máscaras e tamanhos até a versão 35+. |
| Dinheiro em ponto flutuante | `Decimal` com arredondamento bancário explícito: `0.1 + 0.2` vira `0.30`, não `0.30000000000000004`. Aceita `25,90`, `1.234,56` e `R$ 10`. |
| Nome com acento quebra leitores de banco | Nome e cidade vão sem acento, em maiúsculas e cortados nos limites do padrão (25 e 15 caracteres). |
| O campo da conta tem no máximo 99 caracteres | A descrição é limitada ao espaço que sobra depois da chave, e o erro diz quantos caracteres cabem. |
| Planilha do Excel brasileiro | Detecta `;` ou `,` como separador, ignora o BOM do UTF-8 e aponta **a linha** com problema sem parar as outras. |
| QR no terminal escuro e no claro | Meio-bloco (`▀▄█`) com fundo branco forçado por ANSI; `--sem-cor` para terminais sem cor. |
| Ninguém quer digitar a chave toda vez | `pixo config` guarda em `~/.pixo.json`. |
| Sem dependências | Só a biblioteca padrão: `argparse`, `decimal`, `zlib`, `http.server`, `csv`. As dependências de teste (pytest, ZXing) ficam em `[dev]`. |

## Testes

```bash
pip install -e ".[dev]"
pytest
```

64 testes: CRC contra o exemplo do Banco Central, ida e volta (gerar → ler), dígitos verificadores de CPF e CNPJ (inclusive alfanumérico), código adulterado sendo recusado, **QR Codes e PNGs lidos por um leitor real**, todas as máscaras, linha de comando, planilha e a página web. O CI roda em Python 3.10 a 3.13.

---

Feito por **Arthur Martins** · [LinkedIn](https://linkedin.com/in/arthur-martins-2547553b6) · [GitHub](https://github.com/Artas1337)
