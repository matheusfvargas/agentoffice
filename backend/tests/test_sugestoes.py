import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.sugestoes import extrair_opcoes, sugerir_em_partes


class ClienteFalso:
    """Simula a API em modo stream, entregando a resposta em pedaços."""

    def __init__(self, pedacos):
        self.pedidos = []
        self._pedacos = pedacos
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **kwargs):
        self.pedidos.append(kwargs)
        return (
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))])
            for p in self._pedacos
        )


def test_extrair_opcoes():
    texto = "<think>pensando\n- não é opção</think>Claro:\n- A\n2) B\n• C quebrada\ncontinua\n-  \n"
    assert extrair_opcoes(texto) == ["A", "B", "C quebrada continua"]


def test_extrair_opcoes_ignora_raciocinio_ainda_aberto():
    assert extrair_opcoes("<think>\n- rascunho") == []


def test_sugerir_em_partes_entrega_opcoes_aos_poucos():
    cliente = ClienteFalso(["- cresce", "ram 20%.\n- caí", "ram.\n- fica", "ram.\n- quarta\n"])
    partes = list(sugerir_em_partes("As vendas", contexto="# Relatório", cliente=cliente))
    assert partes[0] == ["cresce"]
    assert partes[-1] == ["cresceram 20%.", "caíram.", "ficaram."]
    pedido = cliente.pedidos[0]
    assert pedido["stream"] is True
    assert "As vendas" in pedido["messages"][1]["content"]


def test_sugerir_com_instrucao():
    cliente = ClienteFalso(["- Introdução sobre vendas.\n"])
    partes = list(sugerir_em_partes("", instrucao="escreva uma introdução", cliente=cliente))
    assert partes[-1] == ["Introdução sobre vendas."]
    assert "escreva uma introdução" in cliente.pedidos[0]["messages"][1]["content"]


def test_endpoint_envia_ndjson(monkeypatch):
    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a: iter([["A"], ["A", "B"]]))
    resposta = TestClient(main.app).post("/api/sugestoes", json={"paragrafo": "Oi"})
    linhas = [json.loads(l) for l in resposta.text.splitlines()]
    assert resposta.headers["content-type"].startswith("application/x-ndjson")
    assert linhas == [{"opcoes": ["A"]}, {"opcoes": ["A", "B"]}]


def test_endpoint_envia_erro_do_modelo(monkeypatch):
    def falha(*_):
        raise ConnectionError("recusado")
        yield

    monkeypatch.setattr(main, "sugerir_em_partes", falha)
    resposta = TestClient(main.app).post("/api/sugestoes", json={"paragrafo": "Oi"})
    assert "recusado" in json.loads(resposta.text)["erro"]
