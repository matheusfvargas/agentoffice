"""Fontes de conteúdo do usuário (leis, normas, manuais) usadas nas sugestões.

Os arquivos viram trechos guardados num índice de busca de texto do SQLite (FTS5).
Leis são divididas por artigo, para que o agente possa citar "Art. N" da fonte certa.
"""

import re
import sqlite3
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from . import config

EXTENSOES = {".pdf", ".docx", ".txt", ".md"}
TAMANHO_TRECHO = 1500
# Início de artigo: "Art." com maiúscula no começo da linha. Referências no meio do
# texto ("nos termos do art. 15") usam minúscula e, num PDF, podem cair no começo de
# uma linha quebrada; por isso a busca não ignora maiúsculas.
ARTIGO = re.compile(r"^\s*(Art\.\s*\d+(?:-[A-Z])?\s*[º°o]?)(?=[\s.\-–])", re.MULTILINE)
# Pedido de um dispositivo específico: "art. 15", "artigo 15, V", "art 3º, § 2º".
PEDIDO_DISPOSITIVO = re.compile(
    r"\bart(?:igo)?\.?\s*(\d+)(?:-([a-z]))?\s*[º°o]?"
    r"(?:\s*,?\s*(?:inciso\s+)?([IVXLC]+)\b)?"
    r"(?:\s*,?\s*(?:§|par[aá]grafo)\s*(\d+|[uú]nico))?",
    re.IGNORECASE,
)
INICIO_INCISO = re.compile(r"^\s*([IVXLC]+)\s*[-–—]\s*", re.MULTILINE)
PALAVRAS_VAZIAS = set(
    "a o as os de da do das dos em no na nos nas um uma uns umas e ou que com por para "
    "pelo pela pelos pelas se sobre como mais ao aos à às é ser foi são seu sua seus suas "
    "este esta isto esse essa isso aquele aquela".split()
)


class FonteInvalida(ValueError):
    pass


def _conectar(pasta: Path | None = None) -> sqlite3.Connection:
    pasta = pasta or config.PASTA_DADOS
    pasta.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(pasta / "fontes.db")
    conexao.row_factory = sqlite3.Row
    conexao.executescript(
        """
        CREATE TABLE IF NOT EXISTS fontes (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            total_trechos INTEGER NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS trechos USING fts5(
            fonte_id UNINDEXED, rotulo UNINDEXED, texto,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        """
    )
    return conexao


def extrair_texto(nome: str, conteudo: bytes) -> str:
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES:
        raise FonteInvalida(f"Formato não suportado: {extensao or nome}. Use PDF, DOCX ou TXT.")
    if extensao == ".pdf":
        paginas = PdfReader(BytesIO(conteudo)).pages
        return "\n".join(pagina.extract_text() or "" for pagina in paginas)
    if extensao == ".docx":
        return "\n".join(p.text for p in Document(BytesIO(conteudo)).paragraphs)
    return conteudo.decode("utf-8", errors="replace")


def dividir_em_trechos(texto: str) -> list[tuple[str, str]]:
    """Divide o texto em (rótulo, trecho). Com artigos de lei, um trecho por artigo."""
    texto = re.sub(r"[ \t]+", " ", texto).strip()
    inicios = list(ARTIGO.finditer(texto))
    if len(inicios) >= 2:
        trechos = []
        if inicios[0].start() > 0:
            trechos += _fatiar("Preâmbulo", texto[: inicios[0].start()])
        for atual, proximo in zip(inicios, inicios[1:] + [None]):
            fim = proximo.start() if proximo else len(texto)
            rotulo = re.sub(r"\s+", " ", atual.group(1)).strip()
            trechos += _fatiar(rotulo, texto[atual.start() : fim])
        return trechos
    return [
        (f"trecho {i}", parte)
        for i, (_, parte) in enumerate(_fatiar("", texto), start=1)
    ]


def _fatiar(rotulo: str, texto: str) -> list[tuple[str, str]]:
    """Quebra um texto longo em pedaços de até TAMANHO_TRECHO, respeitando parágrafos."""
    partes, atual = [], ""
    for paragrafo in texto.split("\n"):
        if atual and len(atual) + len(paragrafo) > TAMANHO_TRECHO:
            partes.append(atual.strip())
            atual = ""
        atual += paragrafo + "\n"
    if atual.strip():
        partes.append(atual.strip())
    return [(rotulo, parte) for parte in partes]


def adicionar_fonte(nome: str, conteudo: bytes, pasta: Path | None = None) -> dict:
    trechos = dividir_em_trechos(extrair_texto(nome, conteudo))
    if not trechos:
        raise FonteInvalida(f"Não encontrei texto em {nome}. Se for um PDF escaneado, ele precisa de OCR.")
    with _conectar(pasta) as conexao:
        cursor = conexao.execute("INSERT INTO fontes (nome, total_trechos) VALUES (?, ?)", (nome, len(trechos)))
        fonte_id = cursor.lastrowid
        conexao.executemany(
            "INSERT INTO trechos (fonte_id, rotulo, texto) VALUES (?, ?, ?)",
            [(fonte_id, rotulo, texto) for rotulo, texto in trechos],
        )
    return {"id": fonte_id, "nome": nome, "trechos": len(trechos)}


def listar_fontes(pasta: Path | None = None) -> list[dict]:
    with _conectar(pasta) as conexao:
        return [dict(linha) for linha in conexao.execute("SELECT id, nome, total_trechos AS trechos FROM fontes ORDER BY id")]


def remover_fonte(fonte_id: int, pasta: Path | None = None) -> bool:
    with _conectar(pasta) as conexao:
        conexao.execute("DELETE FROM trechos WHERE fonte_id = ?", (fonte_id,))
        return conexao.execute("DELETE FROM fontes WHERE id = ?", (fonte_id,)).rowcount > 0


def buscar(consulta: str, limite: int = 4, pasta: Path | None = None) -> list[dict]:
    """Devolve os trechos mais relevantes para a consulta (ranking BM25)."""
    termos = {
        t for t in re.findall(r"\w+", consulta.lower())
        if (len(t) > 2 or t.isdigit()) and t not in PALAVRAS_VAZIAS
    }
    if not termos:
        return []
    expressao = " OR ".join(f'"{t}"' for t in sorted(termos))
    with _conectar(pasta) as conexao:
        linhas = conexao.execute(
            """
            SELECT fontes.nome AS fonte, trechos.rotulo, trechos.texto
            FROM trechos JOIN fontes ON fontes.id = trechos.fonte_id
            WHERE trechos MATCH ?
            ORDER BY bm25(trechos)
            LIMIT ?
            """,
            (expressao, limite),
        )
        return [dict(linha) for linha in linhas]


def buscar_dispositivo(pedido: str, pasta: Path | None = None) -> dict | None:
    """Encontra o artigo (e o inciso, se pedido) citado no pedido do usuário.

    Devolve {"fonte", "rotulo", "texto", "inciso"}, onde "inciso" é o texto só do
    inciso pedido (ou None), ou None se o pedido não cita artigo ou ele não está
    nas fontes. Quando há várias fontes com o mesmo artigo, prefere a que tem no nome
    algum número citado no pedido (ex.: "resolução 140/2018" → "...140...").
    """
    citado = PEDIDO_DISPOSITIVO.search(pedido)
    if not citado:
        return None
    numero, letra, inciso, _paragrafo = citado.groups()
    alvo = f"{numero}-{letra.upper()}" if letra else numero
    numeros_no_pedido = set(re.findall(r"\d+", pedido)) - {numero}

    with _conectar(pasta) as conexao:
        linhas = conexao.execute(
            """
            SELECT trechos.rowid, trechos.fonte_id, fontes.nome AS fonte, trechos.rotulo, trechos.texto
            FROM trechos JOIN fontes ON fontes.id = trechos.fonte_id
            WHERE trechos.rotulo LIKE ?
            ORDER BY trechos.rowid
            """,
            (f"Art. {numero}%",),
        ).fetchall()
    candidatos = [l for l in linhas if _numero_do_rotulo(l["rotulo"]) == alvo]
    if not candidatos:
        return None
    candidatos.sort(key=lambda l: not any(n in l["fonte"] for n in numeros_no_pedido))
    primeiro = candidatos[0]
    # Um artigo longo vira vários trechos seguidos com o mesmo rótulo; junta só essa
    # sequência (versões antigas do mesmo artigo, mais adiante no arquivo, ficam de fora).
    partes, rowid = [], primeiro["rowid"]
    for linha in candidatos:
        if linha["fonte_id"] == primeiro["fonte_id"] and linha["rowid"] == rowid:
            partes.append(linha["texto"])
            rowid += 1
    texto = "\n".join(partes)
    return {
        "fonte": primeiro["fonte"],
        "rotulo": primeiro["rotulo"],
        "texto": texto,
        "inciso": extrair_inciso(texto, inciso) if inciso else None,
    }


def _numero_do_rotulo(rotulo: str) -> str:
    achado = re.search(r"(\d+(?:-[A-Z])?)", rotulo)
    return achado.group(1) if achado else ""


def extrair_inciso(texto_artigo: str, inciso: str) -> str | None:
    """Recorta o inciso (ex.: "V") do texto do artigo, até o próximo inciso ou parágrafo."""
    inciso = inciso.upper()
    inicios = list(INICIO_INCISO.finditer(texto_artigo))
    for atual, proximo in zip(inicios, inicios[1:] + [None]):
        if atual.group(1) != inciso:
            continue
        fim = proximo.start() if proximo else len(texto_artigo)
        trecho = texto_artigo[atual.start() : fim]
        # Para no primeiro parágrafo (§ ou "Parágrafo único") depois do inciso.
        corte = re.search(r"^\s*(§|Parágrafo único)", trecho, re.MULTILINE)
        trecho = trecho[: corte.start()] if corte else trecho
        return re.sub(r"\s+", " ", trecho).strip()
    return None
