import pytest

from app import config


@pytest.fixture(autouse=True)
def pasta_dados_temporaria(tmp_path, monkeypatch):
    """Cada teste usa um banco de fontes vazio, fora da pasta do projeto."""
    monkeypatch.setattr(config, "PASTA_DADOS", tmp_path / "dados")
