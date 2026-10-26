import json
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from . import config
from .ferramentas import FUNCOES, SCHEMAS

PROMPT_SISTEMA = """Você é o assistente do agentoffice. O usuário descreve uma tarefa de escritório.
Escolha a ferramenta certa (documento, planilha ou apresentação) e preencha o conteúdo completo.
Escreva em português do Brasil. Se a tarefa não pedir um arquivo, responda só com texto."""

MAX_PASSOS = 4


@dataclass
class Resultado:
    resposta: str = ""
    arquivos: list[Path] = field(default_factory=list)


def criar_cliente() -> OpenAI:
    return OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY)


def executar_tarefa(tarefa: str, cliente: OpenAI | None = None, pasta: Path | None = None) -> Resultado:
    """Roda o loop do agente: o modelo chama ferramentas até dar a resposta final."""
    cliente = cliente or criar_cliente()
    pasta = pasta or config.PASTA_SAIDA
    mensagens = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": tarefa},
    ]
    resultado = Resultado()

    for _ in range(MAX_PASSOS):
        resposta = cliente.chat.completions.create(
            model=config.MODELO, messages=mensagens, tools=SCHEMAS
        )
        mensagem = resposta.choices[0].message
        if not mensagem.tool_calls:
            resultado.resposta = mensagem.content or ""
            return resultado

        mensagens.append(mensagem.model_dump(exclude_none=True))
        for chamada in mensagem.tool_calls:
            conteudo = _executar_ferramenta(chamada, pasta, resultado)
            mensagens.append({"role": "tool", "tool_call_id": chamada.id, "content": conteudo})

    resultado.resposta = "Arquivo gerado." if resultado.arquivos else "O agente não concluiu a tarefa."
    return resultado


def _executar_ferramenta(chamada, pasta: Path, resultado: Resultado) -> str:
    funcao = FUNCOES.get(chamada.function.name)
    if funcao is None:
        return f"Erro: ferramenta desconhecida {chamada.function.name}"
    try:
        argumentos = json.loads(chamada.function.arguments or "{}")
        caminho = funcao(pasta, **argumentos)
    except (json.JSONDecodeError, TypeError, ValueError) as erro:
        # Devolve o erro ao modelo para ele tentar de novo com argumentos corrigidos.
        return f"Erro ao executar {chamada.function.name}: {erro}"
    resultado.arquivos.append(caminho)
    return f"Arquivo criado: {caminho.name}"
