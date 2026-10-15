# AI Regulatory Document Assistant

**Author:** Thalari Sony Prashanthi

Session-only RAG app for company policy Q&A. Upload PDF/DOCX/TXT, ask compliance questions, get grounded answers.

## Privacy

Uploaded documents are **not stored permanently**. They live in server memory for the login session and are wiped on logout, clear, or restart.

## Stack

- **Backend:** FastAPI, JWT auth, Gemini embeddings + chat
- **Fallback:** Local TF-IDF retrieval + extractive answers if Gemini is blocked (403)
- **Frontend:** React + Vite (modern dark glass UI)
- **Deploy:** Render (API) + Vercel (UI)

## Live

- Frontend: https://ai-regulatory-document-assistant.vercel.app
- Backend health: https://ai-regulatory-document-assistant.onrender.com/api/health
- API docs: https://ai-regulatory-document-assistant.onrender.com/docs

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# set GEMINI_API_KEY in .env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Tests

```bash
cd backend
.venv\Scripts\python test_offline.py
```

## Render env vars

| Key | Value |
|-----|--------|
| `PYTHON_VERSION` | `3.12.8` |
| `SECRET_KEY` | auto |
| `GEMINI_API_KEY` | from [AI Studio](https://aistudio.google.com/apikey) |
| `CORS_ORIGINS` | `*` or your Vercel URL |
| `ALLOW_LOCAL_FALLBACK` | `true` |

Root directory: `backend` · Start: `uvicorn main:app --host 0.0.0.0 --port $PORT` · Health: `/api/health`

## Vercel env

`VITE_API_BASE=https://ai-regulatory-document-assistant.onrender.com`

## Gemini 403 denied access

Google sometimes flags free-tier projects. Fix:

1. Age + phone verification + 2SV on the Google account  
2. New key in AI Studio  
3. Enable billing/prepaid if still blocked  
4. Update `GEMINI_API_KEY` on Render and redeploy  

Until then, local fallback still allows upload + Q&A.

## Sample file

`sample_data/sample_company_policy.txt`

## License

MIT · © Thalari Sony Prashanthi
