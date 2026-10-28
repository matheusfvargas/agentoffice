import re

from openai import OpenAI

from . import config
from .agente import criar_cliente

PROMPT_SISTEMA = """Você completa o texto que o usuário está digitando em um editor de documentos.
Responda SOMENTE com a continuação: poucas palavras, no máximo até o fim da frase, no mesmo idioma e tom do texto.
Não repita o que já está escrito, não use aspas e não explique nada."""

PROMPT_COMPLETAR = """Documento até agora:
{contexto}

Parágrafo em que o usuário está digitando:
{texto}"""

# O usuário parou no meio (ou no fim) de uma palavra: pedimos a palavra inteira de volta
# para saber se a continuação termina essa palavra ou começa outra.
PROMPT_PALAVRA = """

O parágrafo termina na palavra "{palavra}", que pode estar incompleta. Comece a resposta escrevendo essa palavra completa e siga com a continuação."""

MAX_CONTEXTO = 2000
MAX_PALAVRAS = 12
ULTIMA_PALAVRA = re.compile(r"(\w+)$")
FIM_DE_FRASE = re.compile(r"(?<=[.!?;:])\s")


def completar(texto: str, contexto: str = "", cliente: OpenAI | None = None) -> str:
    """Continuação curta para o fim de `texto`, pronta para colar logo depois dele.

    Devolve "" quando o modelo não sugere nada aproveitável.
    """
    cliente = cliente or criar_cliente()
    palavra = ULTIMA_PALAVRA.search(texto)
    pedido = PROMPT_COMPLETAR.format(contexto=contexto[-MAX_CONTEXTO:], texto=texto)
    if palavra:
        pedido += PROMPT_PALAVRA.format(palavra=palavra.group(1))
    resposta = cliente.chat.completions.create(
        model=config.MODELO,
        messages=[
            {"role": "system", "content": PROMPT_SISTEMA},
            # /no_think: no Qwen3 desliga o raciocínio, que aqui só atrasaria a sugestão.
            {"role": "user", "content": pedido + "\n/no_think"},
        ],
        temperature=0.3,
        max_tokens=60,
    )
    sugestao = limpar(resposta.choices[0].message.content or "")
    if not sugestao:
        return ""
    if palavra:
        inicio = palavra.group(1)
        if sugestao.lower().startswith(inicio.lower()):
            return sugestao[len(inicio):]
        return " " + sugestao
    if texto and not texto[-1].isspace() and sugestao[0].isalnum():
        return " " + sugestao  # depois de pontuação, a continuação começa uma palavra nova
    return sugestao


def limpar(sugestao: str) -> str:
    """Tira o raciocínio, aspas e quebras de linha e corta no fim da primeira frase."""
    sugestao = re.sub(r"<think>.*?(</think>|$)", "", sugestao, flags=re.DOTALL)
    sugestao = next((linha.strip() for linha in sugestao.splitlines() if linha.strip()), "")
    sugestao = sugestao.strip("\"'“”«»")
    sugestao = FIM_DE_FRASE.split(sugestao, maxsplit=1)[0]
    palavras = sugestao.split(" ")
    return " ".join(palavras[:MAX_PALAVRAS])
