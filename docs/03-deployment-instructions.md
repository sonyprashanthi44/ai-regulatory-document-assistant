# 03 — Deployment Instructions

**Author:** Thalari Sony Prashanthi

## Prerequisites

- GitHub account
- Google AI Studio API key (Gemini)
- Render account (backend) and Vercel account (frontend) — free tiers work

## 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: AI Regulatory Document Assistant"
# create empty repo on GitHub (no README), then:
git branch -M main
git remote add origin https://github.com/<YOUR_USER>/ai-regulatory-document-assistant.git
git push -u origin main
```

Ensure git author is **Thalari Sony Prashanthi** (local `user.name` / `user.email`).

## 2. Deploy backend (Render)

1. New → Web Service → connect this repo
2. Root directory: `backend`
3. Runtime: Python
4. Build: `pip install -r requirements.txt`
5. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Env vars:
   - `SECRET_KEY` = long random string
   - `GEMINI_API_KEY` = your key
   - `CORS_ORIGINS` = your Vercel URL (e.g. `https://xxx.vercel.app`)
7. Deploy and copy the service URL (e.g. `https://ai-reg-api.onrender.com`)

## 3. Deploy frontend (Vercel)

1. Import the GitHub repo in Vercel
2. Root directory: `frontend`
3. Framework: Vite
4. Env: `VITE_API_BASE` = Render backend URL (no trailing slash)
5. Build: `npm run build` · Output: `dist`
6. Deploy

## 4. Wire CORS

Set `CORS_ORIGINS` on Render to the exact Vercel origin and redeploy backend.

## 5. Smoke test

1. Open Vercel URL
2. Register → login
3. Upload `sample_data/sample_company_policy.txt`
4. Ask: “What is the data retention period?”
5. Logout and confirm documents are wiped

## Notes

- Render free tier spins down when idle (cold start ~30–60s)
- Session memory is per backend instance—expected for this design
- Never commit `.env` or real API keys
