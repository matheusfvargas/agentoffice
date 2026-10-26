from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .agente import executar_tarefa

app = FastAPI(title="agentoffice")

PASTA_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


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


@app.get("/api/arquivos/{nome}")
def baixar_arquivo(nome: str) -> FileResponse:
    caminho = (config.PASTA_SAIDA / nome).resolve()
    if caminho.parent != config.PASTA_SAIDA.resolve() or not caminho.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(caminho, filename=nome)


if PASTA_FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=PASTA_FRONTEND, html=True), name="frontend")
