"""Revisão de gramática e ortografia com o LanguageTool.

O LanguageTool é open source, roda localmente (Java) e detecta o idioma do texto.
Aqui ele é usado só por HTTP: este módulo traduz a resposta para o formato do editor.
"""

import httpx

from . import config

# Com idioma automático, qual variante usar quando o texto é de uma língua com várias.
VARIANTES_PREFERIDAS = "pt-BR,en-US,es,de-DE"


class RevisorIndisponivel(RuntimeError):
    pass


def revisar(texto: str, idioma: str = "auto", cliente: httpx.Client | None = None) -> dict:
    """Devolve {"idioma": nome detectado ou escolhido, "erros": [...]}.

    Cada erro tem "inicio" e "tamanho" (posição no texto, em caracteres), "mensagem",
    "sugestoes" (até 5) e "tipo" ("ortografia", "gramatica" ou "estilo").
    """
    dados = {"text": texto, "language": idioma}
    if idioma == "auto":
        dados["preferredVariants"] = VARIANTES_PREFERIDAS
    try:
        if cliente is None:
            with httpx.Client(timeout=20) as cliente_novo:
                resposta = cliente_novo.post(f"{config.LANGUAGETOOL_URL}/v2/check", data=dados)
        else:
            resposta = cliente.post(f"{config.LANGUAGETOOL_URL}/v2/check", data=dados)
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        raise RevisorIndisponivel(
            f"Revisor indisponível em {config.LANGUAGETOOL_URL}. Inicie o LanguageTool (veja o README)."
        ) from erro

    corpo = resposta.json()
    linguagem = corpo.get("language", {})
    nome = linguagem.get("detectedLanguage", {}).get("name") if idioma == "auto" else None
    return {
        "idioma": nome or linguagem.get("name", idioma),
        "erros": [_converter(m) for m in corpo.get("matches", [])],
    }


def _converter(achado: dict) -> dict:
    tipo_lt = achado.get("rule", {}).get("issueType", "")
    tipo = {"misspelling": "ortografia", "style": "estilo", "typographical": "estilo"}.get(tipo_lt, "gramatica")
    return {
        "inicio": achado["offset"],
        "tamanho": achado["length"],
        "mensagem": achado.get("message", ""),
        "sugestoes": [s["value"] for s in achado.get("replacements", [])[:5]],
        "tipo": tipo,
        "regra": achado.get("rule", {}).get("id", ""),
    }
