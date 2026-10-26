"""Fontes de conteúdo do usuário (leis, normas, manuais) usadas nas sugestões.

Os arquivos viram trechos guardados num índice de busca de texto do SQLite (FTS5).
Leis são divididas por artigo, para que o agente possa citar "Art. N" da fonte certa.
"""

import re
import sqlite3
import unicodedata
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
# Começo de cada parte de um artigo: inciso ("V -"), parágrafo ("§ 1º") ou "Parágrafo único".
INICIO_PARTE = re.compile(
    r"^\s*(?:([IVXLC]+)\s*[-–—]|(§\s*\d+\s*[º°o]?)|(Parágrafo único))", re.MULTILINE
)
# Pedido que fala de uma parte de artigo sem dizer qual artigo ("o inciso que trata
# dos efeitos", "o parágrafo do artigo anterior"): vale o artigo citado logo acima.
CITA_PARTE = re.compile(r"\b(incisos?|al[ií]neas?|caput)\b|§", re.IGNORECASE)
CITA_ARTIGO_ANTERIOR = re.compile(
    r"\b(artigo|par[aá]grafo)s?\b.*\b(anterior|acima|mesmo|desse|deste|citado)\b"
    r"|\b(anterior|acima|mesmo|desse|deste|citado)\b.*\b(artigo|par[aá]grafo)s?\b",
    re.IGNORECASE,
)
# Citação que o editor insere depois de um texto da fonte: "(Resolução ..., Art. 15, V)".
CITACAO_NO_TEXTO = re.compile(r"\(([^()]*?),\s*Art\.\s*(\d+(?:-[A-Z])?)[^()]*\)")
# Palavras do próprio pedido que não dizem nada sobre o assunto procurado.
PALAVRAS_DE_COMANDO = {
    "insir", "inser", "inclu", "coloq", "escre", "mostr", "trage", "incis", "artig", "parag",
    "aline", "caput", "anter", "acima", "mesmo", "desse", "deste", "citad", "expli", "trata",
    "sobre", "texto", "resol", "decre", "norma", "segui", "parte", "qual", "aquel",
}
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


def citacao_anterior(contexto: str) -> str | None:
    """Acha o artigo citado nos últimos parágrafos do documento.

    Devolve um pedido equivalente, como "art. 15 140 22 05 2018" (o artigo mais os
    números do nome da fonte, que ajudam a escolher a fonte certa), ou None.
    """
    paragrafos = [p for p in contexto.split("\n") if p.strip()]
    for paragrafo in reversed(paragrafos[-3:]):
        citacoes = list(CITACAO_NO_TEXTO.finditer(paragrafo))
        if citacoes:
            fonte, artigo = citacoes[-1].groups()
            numeros = " ".join(re.findall(r"\d+", fonte))
            return f"art. {artigo} {numeros}"
    return None


def buscar_dispositivo(pedido: str, descricao: str = "", pasta: Path | None = None) -> dict | None:
    """Encontra o artigo (e o inciso, se pedido) citado no pedido do usuário.

    Devolve {"fonte", "rotulo", "texto", "inciso", "partes"} ou None se o pedido não
    cita artigo ou ele não está nas fontes. "inciso" é o texto do inciso pedido pelo
    número; "partes" são os incisos e parágrafos do artigo que tratam do assunto da
    `descricao` (ex.: "o inciso que explica o efeito da exclusão"). Quando há várias
    fontes com o mesmo artigo, prefere a que tem no nome algum número citado no
    pedido (ex.: "resolução 140/2018" → "...140...").
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
        "partes": [] if inciso else partes_sobre(texto, descricao),
    }


def _numero_do_rotulo(rotulo: str) -> str:
    achado = re.search(r"(\d+(?:-[A-Z])?)", rotulo)
    return achado.group(1) if achado else ""


def dividir_partes(texto_artigo: str) -> list[tuple[str, str]]:
    """Divide o artigo em (rótulo, texto): "caput", incisos ("V"), parágrafos ("§ 1º")
    e incisos de parágrafo ("§ 1º, II")."""
    marcas = list(INICIO_PARTE.finditer(texto_artigo))
    fim_caput = marcas[0].start() if marcas else len(texto_artigo)
    partes = [("caput", _limpar(texto_artigo[:fim_caput]))]
    paragrafo_atual = None
    for atual, proximo in zip(marcas, marcas[1:] + [None]):
        inciso, paragrafo, unico = atual.groups()
        if paragrafo or unico:
            paragrafo_atual = re.sub(r"\s+", " ", paragrafo).strip() if paragrafo else "parágrafo único"
            rotulo = paragrafo_atual
        else:
            rotulo = f"{paragrafo_atual}, {inciso}" if paragrafo_atual else inciso
        fim = proximo.start() if proximo else len(texto_artigo)
        partes.append((rotulo, _limpar(texto_artigo[atual.start() : fim])))
    return partes


def extrair_inciso(texto_artigo: str, inciso: str) -> str | None:
    """Texto do inciso do caput (ex.: "V"), sem os incisos e parágrafos seguintes."""
    return next((t for r, t in dividir_partes(texto_artigo) if r == inciso.upper()), None)


def partes_sobre(texto_artigo: str, descricao: str, limite: int = 2) -> list[tuple[str, str]]:
    """Incisos e parágrafos do artigo que mais falam do assunto da descrição.

    Compara radicais (5 primeiras letras, sem acento) e dá mais peso às palavras que
    aparecem em poucas partes do artigo, que são as que distinguem uma parte da outra.
    """
    termos = _radicais(descricao) - PALAVRAS_DE_COMANDO
    partes = [(r, t, _radicais(t)) for r, t in dividir_partes(texto_artigo) if r != "caput"]
    if not termos or not partes:
        return []
    frequencia = {termo: sum(termo in radicais for _, _, radicais in partes) for termo in termos}
    pontuadas = []
    for rotulo, texto, radicais in partes:
        pontos = sum(1 / frequencia[t] for t in termos & radicais)
        if pontos:
            pontuadas.append((pontos, rotulo, texto))
    pontuadas.sort(key=lambda p: -p[0])
    return [(rotulo, texto) for _, rotulo, texto in pontuadas[:limite]]


def _radicais(texto: str) -> set[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return {
        palavra[:5] for palavra in re.findall(r"[a-z]+", sem_acento)
        if len(palavra) > 3 and palavra not in PALAVRAS_VAZIAS
    }


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()
