from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.autocompletar import completar, limpar


class ClienteFalso:
    """Simula a API sem stream, devolvendo sempre a mesma resposta."""

    def __init__(self, resposta):
        self.pedidos = []
        self._resposta = resposta
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **kwargs):
        self.pedidos.append(kwargs)
        mensagem = SimpleNamespace(content=self._resposta)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensagem)])


def test_limpar_corta_na_primeira_frase_e_ignora_raciocinio():
    assert limpar("<think>\n</think>\n\n\"cresceram 20% no trimestre. Depois caíram.\"") == "cresceram 20% no trimestre."


def test_limpar_limita_o_tamanho():
    assert len(limpar(" ".join(["palavra"] * 30)).split()) == 12


def test_depois_de_espaco_a_sugestao_vem_sem_espaco():
    cliente = ClienteFalso("cresceram no trimestre.")
    assert completar("As vendas ", cliente=cliente) == "cresceram no trimestre."
    pedido = cliente.pedidos[0]["messages"][1]["content"]
    assert "As vendas" in pedido and pedido.endswith("/no_think")


def test_termina_a_palavra_incompleta():
    cliente = ClienteFalso("vendas cresceram.")
    assert completar("As ven", cliente=cliente) == "das cresceram."
    assert '"ven"' in cliente.pedidos[0]["messages"][1]["content"]


def test_palavra_completa_ganha_espaco_antes_da_continuacao():
    assert completar("As vendas", cliente=ClienteFalso("vendas cresceram.")) == " cresceram."
    assert completar("As vendas", cliente=ClienteFalso("cresceram.")) == " cresceram."


def test_depois_de_pontuacao_comeca_palavra_nova():
    assert completar("As vendas cresceram,", cliente=ClienteFalso("mas os custos também.")) == " mas os custos também."


def test_resposta_vazia():
    assert completar("Texto ", cliente=ClienteFalso("<think>hmm</think>  ")) == ""


def test_endpoint(monkeypatch):
    monkeypatch.setattr(main, "completar", lambda texto, contexto: f"[{texto}|{contexto}]")
    cliente = TestClient(main.app)
    assert cliente.post("/api/completar", json={"texto": "Oi", "contexto": "# T"}).json() == {"sugestao": "[Oi|# T]"}
    assert cliente.post("/api/completar", json={"texto": "  "}).json() == {"sugestao": ""}


def test_endpoint_sem_modelo(monkeypatch):
    def falha(texto, contexto):
        raise ConnectionError("recusada")

    monkeypatch.setattr(main, "completar", falha)
    resposta = TestClient(main.app).post("/api/completar", json={"texto": "Oi"})
    assert resposta.status_code == 502
