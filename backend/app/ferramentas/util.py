import re
import uuid
from pathlib import Path


def caminho_saida(pasta: Path, titulo: str, extensao: str) -> Path:
    """Gera um nome de arquivo seguro e único a partir do título."""
    pasta.mkdir(parents=True, exist_ok=True)
    base = re.sub(r"[^\w-]+", "-", titulo.lower()).strip("-")[:50] or "arquivo"
    return pasta / f"{base}-{uuid.uuid4().hex[:8]}.{extensao}"
