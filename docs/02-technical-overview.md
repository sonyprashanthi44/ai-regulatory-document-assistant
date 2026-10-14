# 02 — Technical Overview

**Author:** Thalari Sony Prashanthi

## Architecture

```
React (Vite)  --JWT-->  FastAPI
                          |-- auth (in-memory users)
                          |-- upload -> extract -> chunk -> embed (Gemini)
                          |-- query  -> retrieve (cosine) -> generate (Gemini)
                          '-- session store: dict[email] -> chunks in RAM
```

## Backend (`backend/`)

| Module | Role |
|--------|------|
| `main.py` | REST routes, CORS, health |
| `auth.py` | Register/login, bcrypt, JWT |
| `rag.py` | Extract, chunk, embed, retrieve, answer |
| `config.py` | Settings from env |

### API surface

- `POST /api/auth/register`
- `POST /api/auth/login` (OAuth2 password form)
- `POST /api/auth/logout` (wipes session docs)
- `POST /api/documents/upload`
- `GET /api/documents`
- `DELETE /api/documents`
- `POST /api/query`
- `GET /api/health`

### RAG pipeline

1. **Ingest:** PDF (pypdf), DOCX (python-docx), plain text
2. **Chunk:** ~800 chars, 120 overlap
3. **Embed:** Gemini `text-embedding-004`
4. **Store:** NumPy vectors in process memory keyed by user email
5. **Retrieve:** Top-k cosine similarity
6. **Generate:** Gemini `gemini-2.0-flash` with strict context-only prompt

## Frontend (`frontend/`)

- Single-page React app
- Token in `localStorage`
- Privacy banner always visible when logged in
- Author attribution: Thalari Sony Prashanthi

## Security notes

- Passwords hashed with bcrypt
- JWT expiry configurable
- Upload size capped (8MB)
- No document files written to filesystem
- CORS configurable via `CORS_ORIGINS`

## Limitations (honest for interviews)

- In-memory users reset on backend restart (demo-friendly)
- Multi-worker deployments do not share session RAM
- Scanned image-only PDFs need OCR (not included)
- Free Gemini quotas apply

## Why Gemini

Good free tier, strong embeddings + chat in one vendor key, simple Python SDK—fits a portfolio deploy without paid vector DB.
