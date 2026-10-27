import httpx
from fastapi.testclient import TestClient

from app import main, revisao

RESPOSTA_LT = {
    "language": {
        "name": "Portuguese (Brazil)",
        "code": "auto",
        "detectedLanguage": {"name": "Portuguese (Brazil)", "code": "pt-BR"},
    },
    "matches": [
        {
            "message": "Possível erro de ortografia.",
            "offset": 3,
            "length": 6,
            "replacements": [{"value": "exceção"}, {"value": "excepção"}],
            "rule": {"id": "HUNSPELL_RULE", "issueType": "misspelling"},
        },
        {
            "message": "Concordância verbal.",
            "offset": 15,
            "length": 3,
            "replacements": [{"value": f"s{i}"} for i in range(8)],
            "rule": {"id": "CONCORDANCIA", "issueType": "grammar"},
        },
    ],
}


def cliente_falso(pedidos):
    def responder(requisicao: httpx.Request) -> httpx.Response:
        pedidos.append(dict(httpx.QueryParams(requisicao.content.decode())))
        return httpx.Response(200, json=RESPOSTA_LT)

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_revisar_converte_resposta_do_languagetool():
    pedidos = []
    resultado = revisao.revisar("Uma exessao aqui", cliente=cliente_falso(pedidos))
    assert resultado["idioma"] == "Portuguese (Brazil)"
    ortografia, gramatica = resultado["erros"]
    assert ortografia == {
        "inicio": 3, "tamanho": 6, "mensagem": "Possível erro de ortografia.",
        "sugestoes": ["exceção", "excepção"], "tipo": "ortografia", "regra": "HUNSPELL_RULE",
    }
    assert gramatica["tipo"] == "gramatica" and len(gramatica["sugestoes"]) == 5
    assert pedidos[0]["language"] == "auto" and "pt-BR" in pedidos[0]["preferredVariants"]


def test_idioma_escolhido_nao_manda_variantes():
    pedidos = []
    revisao.revisar("texto", idioma="pt-PT", cliente=cliente_falso(pedidos))
    assert pedidos[0]["language"] == "pt-PT" and "preferredVariants" not in pedidos[0]


def test_revisor_fora_do_ar(monkeypatch):
    monkeypatch.setattr(revisao.config, "LANGUAGETOOL_URL", "http://127.0.0.1:9")
    resposta = TestClient(main.app).post("/api/revisao", json={"texto": "Olá"})
    assert resposta.status_code == 503
    assert "LanguageTool" in resposta.json()["detail"]


def test_texto_vazio_nao_chama_revisor():
    assert TestClient(main.app).post("/api/revisao", json={"texto": "  "}).json() == {"idioma": None, "erros": []}
