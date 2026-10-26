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


# Trecho no formato de um PDF salvo do LegisWeb: quebras de linha no meio de frases
# (uma linha começa com "art." minúsculo) e incisos em linhas próprias.
RESOLUCAO = """RESOLUÇÃO CGSN Nº 140, DE 22 DE MAIO DE 2018
Dispõe sobre o Simples Nacional.
Art. 14. A ME ou a EPP pode ser excluída, observado o disposto no
art. 15 desta Resolução.
Art. 15. A exclusão do Simples Nacional, mediante comunicação da ME ou da EPP à RFB, dar-se-á:
I - por opção;
II - obrigatoriamente, quando incorrer em vedação;
V - obrigatoriamente, quando ultrapassado o limite de receita bruta;
§ 1º A exclusão produzirá efeitos a partir do mês seguinte.
§ 2º A comunicação será feita no Portal do Simples Nacional:
I - em até 30 dias;
II - por meio de aplicativo.
Art. 16. Outro assunto.
"""


def test_quebra_de_linha_com_art_minusculo_nao_vira_artigo():
    rotulos = [r for r, _ in fontes.dividir_em_trechos(RESOLUCAO)]
    assert rotulos == ["Preâmbulo", "Art. 14", "Art. 15", "Art. 16"]


def test_buscar_dispositivo_com_inciso():
    fontes.adicionar_fonte("Outra norma.txt", "Art. 15. Texto de outra norma.\nArt. 16. Fim.".encode())
    fontes.adicionar_fonte("Resolução CGSN 140 de 2018.pdf.txt", RESOLUCAO.encode())
    achado = fontes.buscar_dispositivo("insira art. 15, V da resolução 140/2018")
    assert achado["fonte"].startswith("Resolução CGSN 140")
    assert achado["inciso"] == "V - obrigatoriamente, quando ultrapassado o limite de receita bruta;"
    assert fontes.buscar_dispositivo("artigo 15 inciso II da 140")["inciso"].startswith("II - obrigatoriamente")
    assert fontes.buscar_dispositivo("art. 99")is None
    assert fontes.buscar_dispositivo("escreva uma introdução") is None


def test_numeros_curtos_entram_na_busca():
    fontes.adicionar_fonte("Resolução 140.txt", RESOLUCAO.encode())
    assert fontes.buscar("art 15")[0]["rotulo"] in {"Art. 15", "Art. 14"}


def test_endpoint_insere_texto_literal_do_inciso(monkeypatch):
    fontes.adicionar_fonte("Resolução CGSN 140.txt", RESOLUCAO.encode())
    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a, **k: iter([["paráfrase"]]))
    cliente = TestClient(main.app)
    resposta = cliente.post("/api/sugestoes", json={"instrucao": "insira art. 15, V da resolução 140/2018"})
    eventos = [json.loads(l) for l in resposta.text.splitlines()]
    assert eventos[0]["fontes"][0] == "Resolução CGSN 140, Art. 15"
    assert eventos[1]["literais"] == 2
    final = eventos[-1]["opcoes"]
    assert final[0] == "V - obrigatoriamente, quando ultrapassado o limite de receita bruta; (Resolução CGSN 140, Art. 15, V)"
    assert final[1].startswith("Art. 15. A exclusão do Simples Nacional") and "V - obrigatoriamente" in final[1]
    assert "I - por opção" not in final[1]
    assert final[2] == "paráfrase"


def test_endpoint_avisa_artigo_inexistente(monkeypatch):
    fontes.adicionar_fonte("Resolução CGSN 140.txt", RESOLUCAO.encode())
    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a, **k: iter([["x"]]))
    resposta = TestClient(main.app).post("/api/sugestoes", json={"instrucao": "insira art. 99"})
    avisos = [json.loads(l)["aviso"] for l in resposta.text.splitlines() if "aviso" in l]
    assert avisos == ["Não encontrei o art. 99 nas fontes adicionadas."]


def test_citacao_limpa_nome_de_arquivo_salvo_da_web():
    from app.sugestoes import citacao

    trecho = {"fonte": "Resolução CGSN Nº 140 DE 22_05_2018 - Federal - LegisWeb.pdf", "rotulo": "Art. 15"}
    assert citacao(trecho) == "Resolução CGSN Nº 140 DE 22/05/2018, Art. 15"


def test_dividir_partes_do_artigo():
    texto = fontes.dividir_em_trechos(RESOLUCAO)[2][1]
    rotulos = [r for r, _ in fontes.dividir_partes(texto)]
    assert rotulos == ["caput", "I", "II", "V", "§ 1º", "§ 2º", "§ 2º, I", "§ 2º, II"]
    assert fontes.extrair_inciso(texto, "II").startswith("II - obrigatoriamente")


def test_partes_sobre_o_assunto_pedido():
    texto = fontes.dividir_em_trechos(RESOLUCAO)[2][1]
    partes = fontes.partes_sobre(texto, "insira o inciso que explica o efeito da exclusão")
    assert partes[0] == ("§ 1º", "§ 1º A exclusão produzirá efeitos a partir do mês seguinte.")
    assert fontes.partes_sobre(texto, "insira o inciso do artigo anterior") == []


def test_citacao_anterior():
    contexto = (
        "Título\nV - cujo titular participe (Lei Complementar nº 123, de 2006, art. 3º, § 4º) "
        "(Resolução CGSN Nº 140 DE 22/05/2018, Art. 15, V)"
    )
    assert fontes.citacao_anterior(contexto) == "art. 15 140 22 05 2018"
    assert fontes.citacao_anterior("Sem citação nenhuma.") is None


def test_endpoint_usa_artigo_do_paragrafo_anterior(monkeypatch):
    fontes.adicionar_fonte("Outra norma.txt", "Art. 15. Texto de outra norma.\n§ 1º Efeito da exclusão em outra norma.".encode())
    fontes.adicionar_fonte("Resolução CGSN Nº 140 DE 22_05_2018 - Federal - LegisWeb.pdf.txt", RESOLUCAO.encode())
    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a, **k: iter([["paráfrase"]]))
    contexto = "V - obrigatoriamente, quando ultrapassado o limite (Resolução CGSN Nº 140 DE 22/05/2018, Art. 15, V)"
    resposta = TestClient(main.app).post(
        "/api/sugestoes",
        json={"instrucao": "insira o inciso que explica o efeito da exclusão do artigo anterior", "contexto": contexto},
    )
    eventos = [json.loads(l) for l in resposta.text.splitlines()]
    final = eventos[-1]["opcoes"]
    assert final[0] == (
        "§ 1º A exclusão produzirá efeitos a partir do mês seguinte. "
        "(Resolução CGSN Nº 140 DE 22/05/2018, Art. 15, § 1º)"
    )
    assert final[-1] == "paráfrase"


def test_endpoint_avisa_sem_artigo_anterior(monkeypatch):
    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a, **k: iter([["x"]]))
    resposta = TestClient(main.app).post(
        "/api/sugestoes", json={"instrucao": "insira o parágrafo do artigo anterior", "contexto": "Texto livre."}
    )
    assert '"aviso": "Não achei um artigo citado nos parágrafos anteriores."' in resposta.text


def test_pedido_comum_com_paragrafo_nao_busca_artigo(monkeypatch):
    monkeypatch.setattr(main, "sugerir_em_partes", lambda *a, **k: iter([["x"]]))
    contexto = "Algo (Resolução CGSN 140, Art. 15)"
    resposta = TestClient(main.app).post(
        "/api/sugestoes", json={"instrucao": "escreva um parágrafo de conclusão", "contexto": contexto}
    )
    assert "aviso" not in resposta.text and "literais" not in resposta.text
