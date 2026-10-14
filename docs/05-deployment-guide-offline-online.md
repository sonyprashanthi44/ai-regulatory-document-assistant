# 05 — Deployment Guide (Offline & Online)

**Author:** Thalari Sony Prashanthi

## A. Offline / local development

### Requirements

- Python 3.10+
- Node.js 18+
- Gemini API key (online calls still needed for embeddings/LLM unless you swap models)

### Steps

1. Clone the repo
2. Backend:
   - `cd backend && python -m venv .venv`
   - Activate venv
   - `pip install -r requirements.txt`
   - Copy `.env.example` → `.env` and set keys
   - `uvicorn main:app --reload --port 8000`
3. Frontend:
   - `cd frontend && npm install && npm run dev`
4. Browse `http://localhost:5173` (Vite proxies `/api` → `:8000`)

### Fully offline LLM? (optional future)

Replace Gemini with local models (e.g. Ollama embeddings + chat). Current portfolio build intentionally uses Gemini for simple deploy.

### Offline checklist

- [ ] `.env` present, not committed  
- [ ] Backend health: `GET http://127.0.0.1:8000/api/health`  
- [ ] Register/login works  
- [ ] Upload sample policy  
- [ ] Query returns grounded answer  

## B. Online / public portfolio deploy

| Piece | Suggested host |
|-------|----------------|
| Git repo | GitHub |
| API | Render free web service |
| UI | Vercel |
| Secrets | Host env dashboards only |

### Online checklist

- [ ] Repo public with README + docs  
- [ ] Author name **Thalari Sony Prashanthi** on README and UI  
- [ ] `GEMINI_API_KEY` + `SECRET_KEY` set on API host  
- [ ] `VITE_API_BASE` points to API  
- [ ] `CORS_ORIGINS` includes UI origin  
- [ ] Live link added to portfolio  
- [ ] Privacy banner visible  

### Operational expectations

- Cold starts on free API tier  
- Memory wiped when the dyno restarts (aligns with session-only design)  
- Users must re-register after API restart (in-memory auth)  

## C. GitHub Pages? 

Static UI only—**not enough** alone because FastAPI must run somewhere. Prefer Vercel UI + Render API.

## D. One-command local (optional)

```bash
# terminal 1
cd backend && uvicorn main:app --reload --port 8000
# terminal 2
cd frontend && npm run dev
```
