# agentoffice

Ferramentas de escritório com um agente de IA integrado. O usuário descreve a tarefa e o agente gera um documento (.docx), uma planilha (.xlsx) ou uma apresentação (.pptx).

## Como funciona

1. O frontend (`frontend/`) envia a tarefa para `POST /api/tarefa`.
2. O backend (`backend/app/agente.py`) manda a tarefa ao modelo com três ferramentas: `criar_documento`, `criar_planilha` e `criar_apresentacao`.
3. O modelo devolve só o conteúdo em JSON; o código Python (`backend/app/ferramentas/`) monta o arquivo.
4. O arquivo fica disponível em `/api/arquivos/<nome>`.

O backend usa a API compatível com a OpenAI, então funciona com Ollama, llama.cpp, vLLM ou um provedor na nuvem. Para trocar de modelo, basta mudar as variáveis de ambiente.

## Rodando localmente

```bash
# 1. Modelo local (leve, roda na CPU com 16 GB de RAM)
ollama pull qwen3:4b

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ajuste se for usar outro modelo
set -a && source .env && set +a
uvicorn app.main:app --reload
```

Abra http://localhost:8000 e descreva uma tarefa.

## Testes

```bash
cd backend && pytest
```
