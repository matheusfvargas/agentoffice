import json
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .agente import executar_tarefa
from .exportar import documento_para_docx
from . import fontes
from .sugestoes import citacao, sugerir_em_partes

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


@app.post("/api/sugestoes")
def criar_sugestoes(pedido: PedidoSugestao) -> StreamingResponse:
    """Devolve as opções em NDJSON: uma linha {"opcoes": [...]} a cada atualização."""
    if not (pedido.paragrafo.strip() or (pedido.instrucao or "").strip()):
        raise HTTPException(status_code=400, detail="Escreva algo no parágrafo antes de pedir sugestões.")

    # Busca nas fontes pelo pedido ou pelo parágrafo, mais o fim do documento como apoio.
    consulta = f"{pedido.instrucao or pedido.paragrafo} {pedido.contexto[-300:]}"
    trechos = fontes.buscar(consulta)

    def eventos():
        if trechos:
            yield json.dumps({"fontes": [citacao(t) for t in trechos]}, ensure_ascii=False) + "\n"
        try:
            partes = sugerir_em_partes(pedido.paragrafo, pedido.contexto, pedido.instrucao, trechos=trechos)
            for opcoes in partes:
                yield json.dumps({"opcoes": opcoes}, ensure_ascii=False) + "\n"
        except Exception as erro:  # o status 200 já foi enviado; o erro vai como evento
            yield json.dumps({"erro": f"Falha ao falar com o modelo: {erro}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(eventos(), media_type="application/x-ndjson")


@app.get("/api/fontes")
def listar_fontes() -> list[dict]:
    return fontes.listar_fontes()


@app.post("/api/fontes")
async def adicionar_fonte(arquivo: UploadFile) -> dict:
    try:
        return fontes.adicionar_fonte(arquivo.filename or "fonte.txt", await arquivo.read())
    except fontes.FonteInvalida as erro:
        raise HTTPException(status_code=400, detail=str(erro))


@app.delete("/api/fontes/{fonte_id}")
def remover_fonte(fonte_id: int) -> dict:
    if not fontes.remover_fonte(fonte_id):
        raise HTTPException(status_code=404, detail="Fonte não encontrada.")
    return {"ok": True}


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
