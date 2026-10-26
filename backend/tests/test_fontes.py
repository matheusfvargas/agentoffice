import json
from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import fontes, main
from app.sugestoes import sugerir_em_partes
from tests.test_sugestoes import ClienteFalso

LEI = """LEI Nº 9.999, DE 1º DE JANEIRO DE 2026
Dispõe sobre o teletrabalho no serviço público.
Art. 1º Esta Lei regula o teletrabalho dos servidores públicos federais.
Art. 2º O teletrabalho depende de acordo entre o servidor e a chefia imediata.
Parágrafo único. O acordo será revisto a cada seis meses.
Art. 3º O servidor em teletrabalho deve cumprir metas de produtividade.
"""


def test_dividir_lei_por_artigo():
    trechos = fontes.dividir_em_trechos(LEI)
    assert [r for r, _ in trechos] == ["Preâmbulo", "Art. 1º", "Art. 2º", "Art. 3º"]
    assert "seis meses" in trechos[2][1]


def test_dividir_texto_comum_em_pedacos():
    texto = "\n".join(f"Parágrafo {i} " + "x" * 400 for i in range(10))
    trechos = fontes.dividir_em_trechos(texto)
    assert len(trechos) > 1
    assert trechos[0][0] == "trecho 1"
    assert all(len(t) <= fontes.TAMANHO_TRECHO + 500 for _, t in trechos)


def test_adicionar_buscar_e_remover():
    fonte = fontes.adicionar_fonte("Lei 9.999.txt", LEI.encode())
    assert fonte["trechos"] == 4
    resultado = fontes.buscar("acordo com a chefia")
    assert resultado[0]["rotulo"] == "Art. 2º"
    assert resultado[0]["fonte"] == "Lei 9.999.txt"
    # A busca ignora acentos: "produtividade" e "metas" sem diferença de grafia.
    assert fontes.buscar("METAS de produtividade")[0]["rotulo"] == "Art. 3º"
    assert fontes.remover_fonte(fonte["id"]) is True
    assert fontes.buscar("acordo") == []
    assert fontes.listar_fontes() == []


def test_extrair_texto_docx():
    doc = Document()
    doc.add_paragraph("Art. 1º Primeiro.")
    doc.add_paragraph("Art. 2º Segundo.")
    saida = BytesIO()
    doc.save(saida)
    assert "Art. 2º Segundo." in fontes.extrair_texto("lei.docx", saida.getvalue())


def test_formato_invalido():
    with pytest.raises(fontes.FonteInvalida):
        fontes.extrair_texto("planilha.xlsx", b"")


def test_sugestoes_recebem_trechos_e_pedem_citacao():
    fontes.adicionar_fonte("Lei 9.999.txt", LEI.encode())
    trechos = fontes.buscar("teletrabalho chefia")
    cliente = ClienteFalso(["- O teletrabalho depende de acordo (Lei 9.999, Art. 2º).\n"])
    list(sugerir_em_partes("O teletrabalho", trechos=trechos, cliente=cliente))
    pedido = cliente.pedidos[0]["messages"][1]["content"]
    assert "[Lei 9.999, Art. 2º]" in pedido
    assert "não invente" in pedido


def test_endpoints_de_fontes(monkeypatch):
    cliente = TestClient(main.app)
    resposta = cliente.post("/api/fontes", files={"arquivo": ("Lei 9.999.txt", LEI.encode(), "text/plain")})
    assert resposta.status_code == 200
    fonte_id = resposta.json()["id"]
    assert cliente.get("/api/fontes").json()[0]["nome"] == "Lei 9.999.txt"

    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a, **k: iter([["texto"]]))
    eventos = [json.loads(l) for l in cliente.post("/api/sugestoes", json={"paragrafo": "acordo com a chefia"}).text.splitlines()]
    assert eventos[0]["fontes"][0] == "Lei 9.999, Art. 2º"
    assert eventos[1] == {"opcoes": ["texto"]}

    assert cliente.post("/api/fontes", files={"arquivo": ("x.xlsx", b"", "application/octet-stream")}).status_code == 400
    assert cliente.delete(f"/api/fontes/{fonte_id}").status_code == 200
    assert cliente.delete(f"/api/fontes/{fonte_id}").status_code == 404
