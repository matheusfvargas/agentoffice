from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .agente import executar_tarefa
from .exportar import documento_para_docx
from .sugestoes import sugerir

app = FastAPI(title="agentoffice")

PASTA_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class PedidoTarefa(BaseModel):
    tarefa: str


class RespostaTarefa(BaseModel):
    resposta: str
    arquivos: list[str]


@app.post("/api/tarefa", response_model=RespostaTarefa)
def criar_tarefa(pedido: PedidoTarefa) -> RespostaTarefa:
    if not pedido.tarefa.strip():
        raise HTTPException(status_code=400, detail="Descreva a tarefa.")
    resultado = executar_tarefa(pedido.tarefa)
    return RespostaTarefa(
        resposta=resultado.resposta,
        arquivos=[f"/api/arquivos/{caminho.name}" for caminho in resultado.arquivos],
    )


class PedidoSugestao(BaseModel):
    paragrafo: str = ""
    contexto: str = ""
    instrucao: str | None = None


class RespostaSugestao(BaseModel):
    opcoes: list[str]


@app.post("/api/sugestoes", response_model=RespostaSugestao)
def criar_sugestoes(pedido: PedidoSugestao) -> RespostaSugestao:
    if not (pedido.paragrafo.strip() or (pedido.instrucao or "").strip()):
        raise HTTPException(status_code=400, detail="Escreva algo no parágrafo antes de pedir sugestões.")
    opcoes = sugerir(pedido.paragrafo, pedido.contexto, pedido.instrucao)
    return RespostaSugestao(opcoes=opcoes)


class PedidoExportacao(BaseModel):
    documento: dict
    nome: str = "documento"


@app.post("/api/exportar/docx")
def exportar_docx(pedido: PedidoExportacao) -> Response:
    conteudo = documento_para_docx(pedido.documento)
    nome = "".join(c for c in pedido.nome if c.isalnum() or c in " -_").strip() or "documento"
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nome)}.docx"},
    )


@app.get("/api/arquivos/{nome}")
def baixar_arquivo(nome: str) -> FileResponse:
    caminho = (config.PASTA_SAIDA / nome).resolve()
    if caminho.parent != config.PASTA_SAIDA.resolve() or not caminho.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(caminho, filename=nome)


if PASTA_FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=PASTA_FRONTEND, html=True), name="frontend")
