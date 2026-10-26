from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from .util import caminho_saida

SCHEMA = {
    "type": "function",
    "function": {
        "name": "criar_planilha",
        "description": "Cria uma planilha (.xlsx) a partir de um cabeçalho e linhas.",
        "parameters": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "cabecalho": {"type": "array", "items": {"type": "string"}},
                "linhas": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": ["string", "number"]}},
                },
            },
            "required": ["titulo", "cabecalho", "linhas"],
        },
    },
}


def criar_planilha(pasta: Path, titulo: str, cabecalho: list[str], linhas: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = titulo[:31] or "Planilha"
    ws.append(cabecalho)
    for celula in ws[1]:
        celula.font = Font(bold=True)
    for linha in linhas:
        ws.append(linha)
    for coluna in ws.columns:
        largura = max(len(str(c.value or "")) for c in coluna)
        ws.column_dimensions[coluna[0].column_letter].width = min(largura + 2, 60)
    caminho = caminho_saida(pasta, titulo, "xlsx")
    wb.save(caminho)
    return caminho
