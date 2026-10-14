"""Session-scoped RAG. Documents live only in process memory per user session."""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Optional

import google.generativeai as genai
import numpy as np
from pypdf import PdfReader
from docx import Document

from config import get_settings

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
TOP_K = 4


@dataclass
class Chunk:
    text: str
    source: str
    embedding: Optional[np.ndarray] = None


@dataclass
class SessionStore:
    files: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)


# Keyed by user email — wiped on logout / clear
_sessions: dict[str, SessionStore] = {}


def get_session(email: str) -> SessionStore:
    if email not in _sessions:
        _sessions[email] = SessionStore()
    return _sessions[email]


def clear_session(email: str) -> None:
    _sessions.pop(email, None)


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
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _configure_gemini() -> None:
    key = get_settings().gemini_api_key
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    genai.configure(api_key=key)


def _embed(texts: list[str]) -> list[np.ndarray]:
    _configure_gemini()
    out: list[np.ndarray] = []
    for text in texts:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        out.append(np.array(result["embedding"], dtype=np.float32))
    return out


def _embed_query(text: str) -> np.ndarray:
    _configure_gemini()
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_query",
    )
    return np.array(result["embedding"], dtype=np.float32)


def add_document(email: str, filename: str, data: bytes) -> dict:
    text = _extract_text(filename, data)
    pieces = _chunk_text(text)
    if not pieces:
        raise ValueError("No extractable text found in document")

    embeddings = _embed(pieces)
    session = get_session(email)
    # avoid duplicate filename noise — replace same name
    session.chunks = [c for c in session.chunks if c.source != filename]
    if filename in session.files:
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
    scored = [(_cosine(q, c.embedding), c) for c in session.chunks if c.embedding is not None]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:k]]


def answer_query(email: str, question: str) -> dict:
    hits = retrieve(email, question)
    if not hits:
        return {
            "answer": "No documents are loaded in your session. Upload a policy document first. Remember: files exist only for this login session.",
            "sources": [],
            "session_only": True,
        }

    context = "\n\n".join(f"[Source: {h.source}]\n{h.text}" for h in hits)
    _configure_gemini()
    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = f"""You are an enterprise compliance assistant.
Answer ONLY using the provided policy context. If the context is insufficient, say you cannot find it in the uploaded documents.
Be concise and cite source filenames inline.

Context:
{context}

Question: {question}
"""
    response = model.generate_content(prompt)
    answer = (response.text or "").strip()
    sources = sorted({h.source for h in hits})
    return {
        "answer": answer,
        "sources": sources,
        "session_only": True,
        "disclaimer": "Uploaded documents are session-only (in-memory). They are not stored on disk or in any database.",
    }


def session_fingerprint(email: str) -> str:
    """Non-sensitive id for UI — not a storage key on disk."""
    return hashlib.sha256(email.encode()).hexdigest()[:12]
