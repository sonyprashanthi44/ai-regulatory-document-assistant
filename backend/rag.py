"""Session-scoped RAG. Documents live only in process memory per user session."""
from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from pypdf import PdfReader
from docx import Document

from config import get_settings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
TOP_K = 4
# Smaller embedding dims = faster + enough quality for short policy RAG
EMBED_DIM = 768
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Current Gemini models only (legacy embedding-001 / text-embedding-004 were removed).
EMBED_MODELS = (
    "gemini-embedding-001",
    "gemini-embedding-exp-03-07",
)
CHAT_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
)

# Remember which models worked in this process so uploads stay fast after the first call.
_working_embed_model: Optional[str] = None
_working_chat_model: Optional[str] = None


@dataclass
class Chunk:
    text: str
    source: str
    embedding: Optional[list[float]] = None


@dataclass
class SessionStore:
    files: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)


_sessions: dict[str, SessionStore] = {}


def get_session(email: str) -> SessionStore:
    if email not in _sessions:
        _sessions[email] = SessionStore()
    return _sessions[email]


def clear_session(email: str) -> None:
    _sessions.pop(email, None)


def _api_key() -> str:
    key = get_settings().resolved_gemini_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured on the server. "
            "Set it in Render Environment Variables and redeploy."
        )
    return key


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(90.0, connect=20.0),
        headers={"x-goog-api-key": _api_key(), "Content-Type": "application/json"},
    )


def _extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    if name.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Use PDF, DOCX, TXT, or MD.")


def _chunk_text(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _parse_embedding(data: dict) -> Optional[list[float]]:
    """Accept both single and batch-style Gemini embedding responses."""
    emb = data.get("embedding")
    if isinstance(emb, dict) and emb.get("values"):
        return [float(x) for x in emb["values"]]
    if isinstance(emb, list) and emb and isinstance(emb[0], (int, float)):
        return [float(x) for x in emb]
    embs = data.get("embeddings")
    if isinstance(embs, list) and embs:
        first = embs[0]
        if isinstance(first, dict) and first.get("values"):
            return [float(x) for x in first["values"]]
        if isinstance(first, list):
            return [float(x) for x in first]
    return None


def _embed_models_ordered() -> list[str]:
    global _working_embed_model
    models = list(EMBED_MODELS)
    if _working_embed_model and _working_embed_model in models:
        models = [_working_embed_model] + [m for m in models if m != _working_embed_model]
    return models


def _chat_models_ordered() -> list[str]:
    global _working_chat_model
    models = list(CHAT_MODELS)
    if _working_chat_model and _working_chat_model in models:
        models = [_working_chat_model] + [m for m in models if m != _working_chat_model]
    return models


def _embed_one(text: str, task_type: str) -> list[float]:
    """Embed a single string with model + payload fallbacks."""
    global _working_embed_model
    errors: list[str] = []
    payloads = [
        {
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": EMBED_DIM,
        },
        {
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
        },
        {
            "content": {"parts": [{"text": text}]},
        },
    ]
    with _client() as client:
        for model in _embed_models_ordered():
            for body in payloads:
                body = {**body, "model": f"models/{model}"}
                url = f"{GEMINI_BASE}/models/{model}:embedContent"
                try:
                    r = client.post(url, json=body)
                    if r.status_code >= 400:
                        errors.append(f"{model}: HTTP {r.status_code} {r.text[:220]}")
                        if r.status_code == 404:
                            break
                        continue
                    values = _parse_embedding(r.json())
                    if not values:
                        errors.append(f"{model}: empty embedding response")
                        continue
                    _working_embed_model = model
                    return values
                except Exception as e:
                    errors.append(f"{model}: {e}")
                    continue
    detail = " | ".join(errors[-6:]) if errors else "unknown error"
    raise RuntimeError(
        "Embedding failed with all models. "
        "Use a valid GEMINI_API_KEY and ensure gemini-embedding-001 is available. "
        f"Details: {detail}"
    )


def _embed_batch(texts: list[str], task_type: str) -> list[list[float]]:
    """Batch-embed document chunks (much faster than one request per chunk)."""
    global _working_embed_model
    if not texts:
        return []
    if len(texts) == 1:
        return [_embed_one(texts[0], task_type)]

    errors: list[str] = []
    batch_size = 16
    out: list[list[float]] = []

    with _client() as client:
        for start in range(0, len(texts), batch_size):
            slice_texts = texts[start : start + batch_size]
            done = False
            for model in _embed_models_ordered():
                url = f"{GEMINI_BASE}/models/{model}:batchEmbedContents"
                try:
                    r = client.post(
                        url,
                        json={
                            "requests": [
                                {
                                    "model": f"models/{model}",
                                    "content": {"parts": [{"text": t}]},
                                    "taskType": task_type,
                                    "outputDimensionality": EMBED_DIM,
                                }
                                for t in slice_texts
                            ]
                        },
                    )
                    if r.status_code >= 400:
                        r2 = client.post(
                            url,
                            json={
                                "requests": [
                                    {
                                        "model": f"models/{model}",
                                        "content": {"parts": [{"text": t}]},
                                        "taskType": task_type,
                                    }
                                    for t in slice_texts
                                ]
                            },
                        )
                        if r2.status_code >= 400:
                            errors.append(
                                f"{model} batch: HTTP {r.status_code} {r.text[:180]}"
                            )
                            if r.status_code == 404 and r2.status_code == 404:
                                continue
                            out.extend(_embed_one(t, task_type) for t in slice_texts)
                            done = True
                            break
                        r = r2
                    data = r.json()
                    embs = data.get("embeddings") or []
                    if len(embs) != len(slice_texts):
                        errors.append(
                            f"{model} batch: expected {len(slice_texts)} embeddings, got {len(embs)}"
                        )
                        out.extend(_embed_one(t, task_type) for t in slice_texts)
                        done = True
                        break
                    values_list: list[list[float]] = []
                    for e in embs:
                        if isinstance(e, dict) and e.get("values"):
                            values_list.append([float(x) for x in e["values"]])
                        else:
                            values_list = []
                            break
                    if not values_list:
                        out.extend(_embed_one(t, task_type) for t in slice_texts)
                        done = True
                        break
                    _working_embed_model = model
                    out.extend(values_list)
                    done = True
                    break
                except Exception as e:
                    errors.append(f"{model} batch: {e}")
                    continue
            if not done:
                try:
                    out.extend(_embed_one(t, task_type) for t in slice_texts)
                except RuntimeError as e:
                    raise RuntimeError(
                        f"Embedding failed with all models: {e} "
                        f"Prior batch errors: {' | '.join(errors[-4:])}"
                    ) from e
    return out


def _embed(texts: list[str]) -> list[list[float]]:
    return _embed_batch(texts, "RETRIEVAL_DOCUMENT")


def _embed_query(text: str) -> list[float]:
    return _embed_one(text, "RETRIEVAL_QUERY")


def add_document(email: str, filename: str, data: bytes) -> dict:
    text = _extract_text(filename, data)
    pieces = _chunk_text(text)
    if not pieces:
        raise ValueError("No extractable text found in document")

    embeddings = _embed(pieces)
    session = get_session(email)
    session.chunks = [c for c in session.chunks if c.source != filename]
    session.files = [f for f in session.files if f != filename]
    session.files.append(filename)
    for piece, emb in zip(pieces, embeddings):
        session.chunks.append(Chunk(text=piece, source=filename, embedding=emb))
    return {
        "filename": filename,
        "chunks": len(pieces),
        "session_files": list(session.files),
        "embed_model": _working_embed_model,
        "note": (
            "Document is kept in memory for this login session only and is never "
            "written to disk or a database."
        ),
    }


def list_documents(email: str) -> list[str]:
    return list(get_session(email).files)


def _cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for i in range(n):
        x = a[i]
        y = b[i]
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom < 1e-12:
        return 0.0
    return float(dot / denom)


def retrieve(email: str, query: str, k: int = TOP_K) -> list[Chunk]:
    session = get_session(email)
    if not session.chunks:
        return []
    q = _embed_query(query)
    scored = [
        (_cosine(q, c.embedding), c)
        for c in session.chunks
        if c.embedding is not None
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def _generate(prompt: str) -> str:
    global _working_chat_model
    errors: list[str] = []
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }
    with _client() as client:
        for model in _chat_models_ordered():
            url = f"{GEMINI_BASE}/models/{model}:generateContent"
            try:
                r = client.post(url, json=body)
                if r.status_code >= 400:
                    errors.append(f"{model}: HTTP {r.status_code} {r.text[:220]}")
                    continue
                data = r.json()
                parts = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [])
                )
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    _working_chat_model = model
                    return text
                finish = data.get("candidates", [{}])[0].get("finishReason", "")
                errors.append(f"{model}: empty generation (finishReason={finish})")
            except Exception as e:
                errors.append(f"{model}: {e}")
                continue
    detail = " | ".join(errors[-6:]) if errors else "unknown error"
    raise RuntimeError(f"Generation failed with all models. Details: {detail}")


def answer_query(email: str, question: str) -> dict:
    hits = retrieve(email, question)
    if not hits:
        return {
            "answer": (
                "No documents are loaded in your session. Upload a policy document first. "
                "Remember: files exist only for this login session."
            ),
            "sources": [],
            "session_only": True,
        }

    context = "\n\n".join(f"[Source: {h.source}]\n{h.text}" for h in hits)
    prompt = f"""You are an enterprise compliance assistant.
Answer ONLY using the provided policy context. If the context is insufficient, say you cannot find it in the uploaded documents.
Be concise and cite source filenames inline.

Context:
{context}

Question: {question}
"""
    answer = _generate(prompt)
    sources = sorted({h.source for h in hits})
    return {
        "answer": answer,
        "sources": sources,
        "session_only": True,
        "chat_model": _working_chat_model,
        "disclaimer": (
            "Uploaded documents are session-only (in-memory). "
            "They are not stored on disk or in any database."
        ),
    }


def session_fingerprint(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:12]


def gemini_status() -> dict:
    """Lightweight diagnostics for /api/health (does not call paid endpoints)."""
    return {
        "embed_models": list(EMBED_MODELS),
        "chat_models": list(CHAT_MODELS),
        "working_embed_model": _working_embed_model,
        "working_chat_model": _working_chat_model,
        "gemini_configured": bool(get_settings().resolved_gemini_key()),
    }
