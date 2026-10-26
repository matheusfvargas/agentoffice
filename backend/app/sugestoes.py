import re
from collections.abc import Iterator

from openai import OpenAI

from . import config
from .agente import criar_cliente

PROMPT_SISTEMA = """Você é um assistente de escrita dentro de um editor de documentos.
Você recebe o documento até agora e o parágrafo em que o usuário está escrevendo.
Escreva em português do Brasil, no mesmo tom do documento.
Responda SOMENTE com {n} opções diferentes entre si, uma por linha, cada linha começando com "- ".
Não escreva nada antes nem depois das opções."""

PROMPT_CONTINUAR = """Documento até agora:
{contexto}

Parágrafo atual:
{paragrafo}

Sugira {n} formas de completar ou continuar o parágrafo atual. Cada opção é só o texto que vem depois do que já está escrito."""

PROMPT_INSTRUCAO = """Documento até agora:
{contexto}

O usuário pediu, para este ponto do documento: {instrucao}

Escreva {n} versões do parágrafo pedido. Cada opção é o parágrafo completo, em uma única linha."""

MAX_CONTEXTO = 6000
MARCADOR_OPCAO = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def sugerir_em_partes(
    paragrafo: str,
    contexto: str = "",
    instrucao: str | None = None,
    n: int = 3,
    cliente: OpenAI | None = None,
) -> Iterator[list[str]]:
    """Pede ao modelo `n` opções para o parágrafo atual e devolve a lista parcial
    a cada trecho recebido, para a tela mostrar as opções enquanto são escritas.

    Sem `instrucao`, as opções continuam o parágrafo; com `instrucao`, cada opção
    é um parágrafo novo que atende ao pedido.
    """
    cliente = cliente or criar_cliente()
    # Mantém só o final do documento: é o trecho mais relevante para o parágrafo atual.
    contexto = contexto[-MAX_CONTEXTO:]
    if instrucao:
        pedido = PROMPT_INSTRUCAO.format(contexto=contexto, instrucao=instrucao, n=n)
    else:
        pedido = PROMPT_CONTINUAR.format(contexto=contexto, paragrafo=paragrafo, n=n)

    fluxo = cliente.chat.completions.create(
        model=config.MODELO,
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA.format(n=n)},
            {"role": "user", "content": pedido},
        ],
        temperature=0.8,
        stream=True,
    )
    texto = ""
    ultimas: list[str] = []
    for parte in fluxo:
        if not parte.choices:
            continue
        texto += parte.choices[0].delta.content or ""
        opcoes = extrair_opcoes(texto)[:n]
        if opcoes != ultimas:
            ultimas = opcoes
            yield opcoes


def extrair_opcoes(texto: str) -> list[str]:
    """Lê as opções (uma por linha) do texto recebido até agora.

    Ignora o raciocínio entre <think> e </think>, inclusive um bloco ainda aberto,
    e aceita linhas com "-", "*", "•" ou numeradas.
    """
    texto = re.sub(r"<think>.*?(</think>|$)", "", texto, flags=re.DOTALL)
    opcoes = []
    for linha in texto.splitlines():
        if MARCADOR_OPCAO.match(linha):
            opcoes.append(MARCADOR_OPCAO.sub("", linha, count=1).strip())
        elif opcoes and linha.strip():
            # Linha sem marcador continua a opção anterior (modelo quebrou a linha).
            opcoes[-1] = f"{opcoes[-1]} {linha.strip()}"
    return [o for o in opcoes if o]
