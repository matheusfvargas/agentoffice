# agentoffice

Editor de documentos com um agente de IA integrado. Enquanto escreve, o usuário pede ao agente opções para completar o parágrafo atual, ou descreve o que quer naquele ponto e escolhe entre as versões sugeridas. O documento é exportado para .docx.

## Como usar o editor

- **Completar um parágrafo:** escreva o começo e aperte `Ctrl+Espaço` (ou o botão *Sugerir*). O agente mostra 3 continuações; escolha com `1`, `2`, `3` ou com o mouse. `Esc` fecha.
- **Pedir algo:** comece o parágrafo com `/` e descreva o que quer, por exemplo `/escreva uma introdução sobre as vendas do trimestre`. A opção escolhida substitui o pedido.
- **Usar suas fontes:** no painel *Fontes*, adicione leis, normas ou manuais (PDF, DOCX ou TXT). A cada pedido, o agente busca os trechos mais relevantes, usa esse conteúdo nas opções e cita a fonte e o artigo, por exemplo *(Lei 8.112, Art. 5º)*. O painel de sugestões mostra quais trechos foram consultados.
- **Exportar:** o botão *Exportar .docx* baixa o documento com títulos, listas, negrito, itálico e tabelas.

## Estrutura

- `frontend/`: editor em JavaScript com [TipTap](https://tiptap.dev) e Vite. O painel de sugestões fica em `src/sugestoes.js`.
- `backend/app/sugestoes.py`: monta o pedido ao modelo e lê as opções em JSON (`POST /api/sugestoes`).
- `backend/app/fontes.py`: lê os arquivos de fontes, divide leis por artigo e guarda os trechos num índice de busca do SQLite (FTS5) em `backend/dados/` (`/api/fontes`).
- `backend/app/exportar.py`: converte o documento do editor para .docx (`POST /api/exportar/docx`).
- `backend/app/agente.py` e `backend/app/ferramentas/`: agente que gera arquivos inteiros a partir de uma tarefa (`POST /api/tarefa`). Fica como base para os próximos editores, como o de slides.

O backend usa a API compatível com a OpenAI, então funciona com Ollama, llama.cpp, vLLM ou um provedor na nuvem. Para trocar de modelo, basta mudar as variáveis de ambiente (veja `backend/.env.example`).

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

# 3. Frontend (em outro terminal)
cd frontend
npm install
npm run dev
```

Abra http://localhost:5173. O Vite repassa as chamadas `/api` para o backend na porta 8000.

Para servir tudo pelo backend, rode `npm run build` em `frontend/` e abra http://localhost:8000.

## Testes

```bash
cd backend && pytest
```
