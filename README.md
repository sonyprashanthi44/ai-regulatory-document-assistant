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
| LLM | Google Gemini (`gemini-2.0-flash` + `gemini-embedding-001`) |
| Auth | Register / login with JWT bearer tokens |

## Features

- Register / login (authenticated REST APIs)
- Upload PDF, DOCX, TXT, MD, CSV (session-only)
- Natural-language Q&A grounded in uploaded policies
- Source citations
- Explicit session wipe on logout

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
npm run dev
```

Open http://localhost:5173


## Live demo

After deployment, add your live URL here:

- Frontend: _pending deploy_
- Backend API docs: _pending deploy_/docs

## Sample document

Use `sample_data/sample_company_policy.txt` to try Q&A without real confidential files.

## License

MIT · © Thalari Sony Prashanthi

