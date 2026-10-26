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

PROMPT_FONTES = """Trechos das fontes do usuário que podem ser relevantes:
{trechos}

Quando usar uma informação desses trechos, cite a fonte no fim da frase, no formato ({rotulo_exemplo}).
Use só o que está nos trechos; não invente artigos, números ou leis."""

MAX_CONTEXTO = 6000
MARCADOR_OPCAO = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def sugerir_em_partes(
    paragrafo: str,
    contexto: str = "",
    instrucao: str | None = None,
    n: int = 3,
    trechos: list[dict] | None = None,
    cliente: OpenAI | None = None,
) -> Iterator[list[str]]:
    """Pede ao modelo `n` opções para o parágrafo atual e devolve a lista parcial
    a cada trecho recebido, para a tela mostrar as opções enquanto são escritas.

    Sem `instrucao`, as opções continuam o parágrafo; com `instrucao`, cada opção
    é um parágrafo novo que atende ao pedido. `trechos` são passagens das fontes
    do usuário (veja `fontes.buscar`) que o modelo deve usar e citar.
    """
    cliente = cliente or criar_cliente()
    # Mantém só o final do documento: é o trecho mais relevante para o parágrafo atual.
    contexto = contexto[-MAX_CONTEXTO:]
    if instrucao:
        pedido = PROMPT_INSTRUCAO.format(contexto=contexto, instrucao=instrucao, n=n)
    else:
        pedido = PROMPT_CONTINUAR.format(contexto=contexto, paragrafo=paragrafo, n=n)
    if trechos:
        pedido += "\n\n" + PROMPT_FONTES.format(
            trechos="\n\n".join(f"[{citacao(t)}]\n{t['texto']}" for t in trechos),
            rotulo_exemplo=citacao(trechos[0]),
        )

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


def citacao(trecho: dict) -> str:
    """Como o trecho é citado no texto, ex.: "Lei 8.112, Art. 5º"."""
    nome = re.sub(r"\.(pdf|docx|txt|md)$", "", trecho["fonte"], flags=re.IGNORECASE)
    # Nomes de arquivos salvos de sites trazem sufixos ("... - Federal - LegisWeb") e
    # datas com "_" no lugar de "/" ("22_05_2018"); fica só o nome da norma.
    nome = nome.split(" - ")[0].strip()
    nome = re.sub(r"(\d{1,2})_(\d{1,2})_(\d{4})", r"\1/\2/\3", nome)
    return f"{nome}, {trecho['rotulo']}" if trecho["rotulo"] else nome


def opcoes_literais(dispositivo: dict) -> list[str]:
    """Opções com o texto exato do dispositivo pedido, sem passar pelo modelo.

    Com inciso: o inciso sozinho e o caput seguido do inciso. Sem inciso: o artigo inteiro.
    """
    fonte = citacao({"fonte": dispositivo["fonte"], "rotulo": ""})
    texto = re.sub(r"\s+", " ", dispositivo["texto"]).strip()
    inciso = dispositivo["inciso"]
    if not inciso:
        return [f"{texto} ({fonte})"]
    caput = re.split(r"\s(?=[IVXLC]+\s*[-–—]\s)", texto, maxsplit=1)[0].strip()
    return [
        f"{inciso} ({fonte}, {dispositivo['rotulo']})",
        f"{caput} {inciso} ({fonte})",
    ]


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
