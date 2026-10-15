# AI Regulatory Document Assistant

**Author:** Thalari Sony Prashanthi

Secure web app for uploading company policy documents and querying them in natural language using a **RAG (Retrieval-Augmented Generation)** pipeline.

## Privacy-first design

**Uploaded documents are NOT stored anywhere permanent.**

- Files are processed in memory only
- Chunks + embeddings live in the active login session
- Cleared on logout, manual clear, or server restart
- No disk writes, no object storage, no document database

This is stated clearly in the UI banner and API responses.

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI, JWT auth, in-memory session RAG |
| Frontend | React (Vite) |
| LLM | Google Gemini (`gemini-2.5-flash` / `gemini-2.0-flash` + `gemini-embedding-001`) |
| Auth | Register / login with JWT bearer tokens |

## Features

- Register / login (authenticated REST APIs)
- Upload PDF, DOCX, TXT, MD, CSV (session-only)
- Natural-language Q&A grounded in uploaded policies
- Source citations
- Explicit session wipe on logout

## Live demo

- Frontend: https://ai-regulatory-document-assistant.vercel.app
- Backend health: https://ai-regulatory-document-assistant.onrender.com/api/health
- API docs: https://ai-regulatory-document-assistant.onrender.com/docs

## Quick start (local)

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# set GEMINI_API_KEY and SECRET_KEY in .env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
# optional: set VITE_API_BASE=http://127.0.0.1:8000
npm run dev
```

Open http://localhost:5173

### Offline tests

```bash
cd backend
.venv\Scripts\python test_offline.py
.venv\Scripts\python test_rag_mock.py
```

## Deploy notes

### Render (backend)

1. New Web Service from this repo
2. **Root Directory:** `backend` (or use root `render.yaml`)
3. Build: `pip install --upgrade pip && pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`
5. Health check path: `/api/health`
6. Env vars:
   - `PYTHON_VERSION=3.12.8`
   - `SECRET_KEY` (auto-generate)
   - `GEMINI_API_KEY` = your Google AI Studio key (**required** for upload/query)
   - `CORS_ORIGINS=*` (or your Vercel URL)

**Important:** Free Render instances sleep when idle — the first request after sleep can take 30–60s. Builds should be a few minutes after numpy was removed from dependencies.

### Vercel (frontend)

1. Root Directory: `frontend`
2. Build: `npm run build`
3. Output: `dist`
4. Env: `VITE_API_BASE=https://ai-regulatory-document-assistant.onrender.com`

## Sample document

Use `sample_data/sample_company_policy.txt` to try Q&A without real confidential files.

## License

MIT · © Thalari Sony Prashanthi
