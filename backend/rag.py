"""Session-scoped RAG. Documents live only in process memory per user session."""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
import numpy as np
from pypdf import PdfReader
from docx import Document

from config import get_settings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
TOP_K = 4
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Prefer current models; fall back if a key/region lacks one
EMBED_MODELS = (
    "gemini-embedding-001",
    "embedding-001",
)
CHAT_MODELS = (
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-flash-latest",
)


@dataclass
class Chunk:
    text: str
    source: str
    embedding: Optional[np.ndarray] = None


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


def _embed_one(text: str, task_type: str) -> np.ndarray:
    key = _api_key()
    last_err: Exception | None = None
    payload_task = task_type.upper()  # RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY
    for model in EMBED_MODELS:
        url = f"{GEMINI_BASE}/models/{model}:embedContent"
        body = {
            "model": f"models/{model}",
            "content": {"parts": [{"text": text}]},
            "taskType": payload_task,
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(url, params={"key": key}, json=body)
            if r.status_code >= 400:
                last_err = RuntimeError(f"{model}: {r.status_code} {r.text[:300]}")
                continue
            data = r.json()
            values = (
                data.get("embedding", {}).get("values")
                or data.get("embeddings", [{}])[0].get("values")
            )
            if not values:
                last_err = RuntimeError(f"{model}: empty embedding in response")
                continue
            return np.array(values, dtype=np.float32)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Embedding failed: {last_err}")


def _embed(texts: list[str]) -> list[np.ndarray]:
    return [_embed_one(t, "RETRIEVAL_DOCUMENT") for t in texts]


def _embed_query(text: str) -> np.ndarray:
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
        "note": "Document is kept in memory for this login session only and is never written to disk or a database.",
    }


def list_documents(email: str) -> list[str]:
    return list(get_session(email).files)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


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
    key = _api_key()
    last_err: Exception | None = None
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }
    for model in CHAT_MODELS:
        url = f"{GEMINI_BASE}/models/{model}:generateContent"
        try:
            with httpx.Client(timeout=90.0) as client:
                r = client.post(url, params={"key": key}, json=body)
            if r.status_code >= 400:
                last_err = RuntimeError(f"{model}: {r.status_code} {r.text[:300]}")
                continue
            data = r.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                return text
            last_err = RuntimeError(f"{model}: empty generation response")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Generation failed: {last_err}")


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
        "disclaimer": (
            "Uploaded documents are session-only (in-memory). "
            "They are not stored on disk or in any database."
        ),
    }


def session_fingerprint(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:12]

