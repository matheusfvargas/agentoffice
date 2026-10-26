import json
from types import SimpleNamespace

from app.agente import executar_tarefa


class ClienteFalso:
    """Simula a API: primeiro pede uma planilha, depois responde com texto."""

    def __init__(self, respostas):
        self._respostas = iter(respostas)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **_):
        return SimpleNamespace(choices=[SimpleNamespace(message=next(self._respostas))])


class Mensagem(SimpleNamespace):
    def model_dump(self, exclude_none=False):
        return {"role": "assistant", "content": self.content}


def chamada(nome, argumentos):
    return SimpleNamespace(id="1", function=SimpleNamespace(name=nome, arguments=json.dumps(argumentos)))


def test_agente_gera_planilha(tmp_path):
    args = {"titulo": "Orçamento", "cabecalho": ["Item", "Valor"], "linhas": [["A", 1]]}
    cliente = ClienteFalso([
        Mensagem(content=None, tool_calls=[chamada("criar_planilha", args)]),
        Mensagem(content="Pronto, criei a planilha.", tool_calls=None),
    ])
    resultado = executar_tarefa("monte um orçamento", cliente=cliente, pasta=tmp_path)
    assert resultado.resposta == "Pronto, criei a planilha."
    assert len(resultado.arquivos) == 1 and resultado.arquivos[0].suffix == ".xlsx"


def test_agente_devolve_erro_de_argumentos_ao_modelo(tmp_path):
    cliente = ClienteFalso([
        Mensagem(content=None, tool_calls=[chamada("criar_planilha", {"titulo": "X"})]),
        Mensagem(content="Não consegui.", tool_calls=None),
    ])
    resultado = executar_tarefa("planilha", cliente=cliente, pasta=tmp_path)
    assert resultado.arquivos == []
    assert resultado.resposta == "Não consegui."
