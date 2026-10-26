from types import SimpleNamespace

from app.sugestoes import extrair_opcoes, sugerir


class ClienteFalso:
    def __init__(self, conteudo):
        self.pedidos = []
        self._conteudo = conteudo
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **kwargs):
        self.pedidos.append(kwargs)
        mensagem = SimpleNamespace(content=self._conteudo)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensagem)])


def test_extrair_opcoes_ignora_texto_extra():
    texto = '<think>pensando</think>Claro! {"opcoes": ["A", " B ", "", 3]} fim'
    assert extrair_opcoes(texto) == ["A", "B"]


def test_extrair_opcoes_json_invalido():
    assert extrair_opcoes("sem json aqui") == []
    assert extrair_opcoes("{quebrado") == []


def test_sugerir_continuar_paragrafo():
    cliente = ClienteFalso('{"opcoes": ["um", "dois", "três", "quatro"]}')
    opcoes = sugerir("O projeto tem", contexto="# Relatório", cliente=cliente)
    assert opcoes == ["um", "dois", "três"]
    pedido = cliente.pedidos[0]["messages"][1]["content"]
    assert "O projeto tem" in pedido and "completar" in pedido


def test_sugerir_com_instrucao():
    cliente = ClienteFalso('{"opcoes": ["Introdução sobre vendas."]}')
    opcoes = sugerir("", instrucao="escreva uma introdução sobre vendas", cliente=cliente)
    assert opcoes == ["Introdução sobre vendas."]
    assert "escreva uma introdução" in cliente.pedidos[0]["messages"][1]["content"]
