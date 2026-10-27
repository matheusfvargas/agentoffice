import os
from pathlib import Path

BASE_URL = os.getenv("AGENTOFFICE_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.getenv("AGENTOFFICE_API_KEY", "ollama")
MODELO = os.getenv("AGENTOFFICE_MODELO", "qwen3:4b")
PASTA_SAIDA = Path(os.getenv("AGENTOFFICE_PASTA_SAIDA", "saida"))
PASTA_DADOS = Path(os.getenv("AGENTOFFICE_PASTA_DADOS", "dados"))
LANGUAGETOOL_URL = os.getenv("AGENTOFFICE_LANGUAGETOOL_URL", "http://localhost:8081")
