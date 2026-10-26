"""Ferramentas que o agente pode chamar.

Cada ferramenta tem um schema (enviado ao modelo) e uma função que recebe
os argumentos já decodificados e devolve o caminho do arquivo gerado.
"""

from .apresentacao import SCHEMA as SCHEMA_APRESENTACAO, criar_apresentacao
from .documento import SCHEMA as SCHEMA_DOCUMENTO, criar_documento
from .planilha import SCHEMA as SCHEMA_PLANILHA, criar_planilha

SCHEMAS = [SCHEMA_DOCUMENTO, SCHEMA_PLANILHA, SCHEMA_APRESENTACAO]

FUNCOES = {
    "criar_documento": criar_documento,
    "criar_planilha": criar_planilha,
    "criar_apresentacao": criar_apresentacao,
}
