import json
import re

from openai import OpenAI

from . import config
from .agente import criar_cliente

PROMPT_SISTEMA = """Você é um assistente de escrita dentro de um editor de documentos.
Você recebe o documento até agora e o parágrafo em que o usuário está escrevendo.
Escreva em português do Brasil, no mesmo tom do documento.
Responda SOMENTE com JSON no formato {"opcoes": ["...", "...", "..."]}, com {n} opções diferentes entre si."""

PROMPT_CONTINUAR = """Documento até agora:
{contexto}

Parágrafo atual:
{paragrafo}

Sugira {n} formas de completar ou continuar o parágrafo atual. Cada opção é só o texto que vem depois do que já está escrito."""

PROMPT_INSTRUCAO = """Documento até agora:
{contexto}

O usuário pediu, para este ponto do documento: {instrucao}

Escreva {n} versões do parágrafo pedido. Cada opção é o parágrafo completo."""

MAX_CONTEXTO = 6000


def sugerir(
    paragrafo: str,
    contexto: str = "",
    instrucao: str | None = None,
    n: int = 3,
    cliente: OpenAI | None = None,
) -> list[str]:
    """Pede ao modelo `n` opções para o parágrafo atual.

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

    resposta = cliente.chat.completions.create(
        model=config.MODELO,
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA.replace("{n}", str(n))},
            {"role": "user", "content": pedido},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
    )
    return extrair_opcoes(resposta.choices[0].message.content or "")[:n]


def extrair_opcoes(texto: str) -> list[str]:
    """Lê a lista de opções da resposta, tolerando texto extra ao redor do JSON."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fim <= inicio:
        return []
    try:
        dados = json.loads(texto[inicio : fim + 1])
    except json.JSONDecodeError:
        return []
    opcoes = dados.get("opcoes", []) if isinstance(dados, dict) else []
    return [o.strip() for o in opcoes if isinstance(o, str) and o.strip()]
