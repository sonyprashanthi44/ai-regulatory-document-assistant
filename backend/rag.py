"""Session-only RAG: Gemini embeddings + chat, with local TF-IDF fallback."""
from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import httpx
from docx import Document
from pypdf import PdfReader

from config import get_settings

CHUNK_SIZE = 900
CHUNK_OVERLAP = 140
TOP_K = 5
EMBED_DIM = 768
LOCAL_DIM = 384
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

EMBED_MODELS = (
    "gemini-embedding-001",
    "gemini-embedding-2",
    "gemini-embedding-2-preview",
)
CHAT_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-2.5-flash",
)

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.I)
_STOP = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her",
    "was", "one", "our", "out", "has", "have", "been", "from", "they", "this",
    "that", "with", "will", "what", "when", "your", "which", "their", "there",
    "about", "into", "than", "then", "them", "these", "those", "would", "could",
    "should", "a", "an", "of", "to", "in", "on", "is", "it", "as", "at", "by",
    "or", "if", "be", "we", "do", "no", "so", "up",
}

_working_embed_model: Optional[str] = None
_working_chat_model: Optional[str] = None
_gemini_embed_blocked = False
_gemini_chat_blocked = False
_last_error = ""


@dataclass
class Chunk:
    text: str
    source: str
    embedding: Optional[list[float]] = None


@dataclass
class SessionStore:
    files: list[str] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    retrieval_mode: str = "unknown"


_sessions: dict[str, SessionStore] = {}


def get_session(email: str) -> SessionStore:
    if email not in _sessions:
        _sessions[email] = SessionStore()
    return _sessions[email]


def clear_session(email: str) -> None:
    _sessions.pop(email, None)


def _settings():
    return get_settings()


def _api_key() -> str:
    key = _settings().resolved_gemini_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it in Render Environment, or rely on local fallback."
        )
    return key


def _has_key() -> bool:
    return bool(_settings().resolved_gemini_key())


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(75.0, connect=20.0),
        headers={"x-goog-api-key": _api_key(), "Content-Type": "application/json"},
    )


def _denied(status: int, body: str) -> bool:
    if status == 403:
        return True
    b = (body or "").lower()
    return "permission_denied" in b or "denied access" in b


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
    raise ValueError("Unsupported file type. Use PDF, DOCX, TXT, MD, or CSV.")


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


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def _local_embed(text: str) -> list[float]:
    toks = _tokenize(text)
    vec = [0.0] * LOCAL_DIM
    if not toks:
        return vec
    counts = Counter(toks)
    n = float(len(toks))
    for tok, c in counts.items():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % LOCAL_DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign * (c / n)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _parse_embedding(data: dict) -> Optional[list[float]]:
    emb = data.get("embedding")
    if isinstance(emb, dict) and emb.get("values"):
        return [float(x) for x in emb["values"]]
    embs = data.get("embeddings")
    if isinstance(embs, list) and embs:
        first = embs[0]
        if isinstance(first, dict) and first.get("values"):
            return [float(x) for x in first["values"]]
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = na = nb = 0.0
    for i in range(n):
        x, y = a[i], b[i]
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    return float(dot / denom) if denom > 1e-12 else 0.0


def _embed_one_gemini(text: str, task_type: str) -> list[float]:
    global _working_embed_model, _gemini_embed_blocked, _last_error
    payloads = [
        {
            "model": f"models/{EMBED_MODELS[0]}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": EMBED_DIM,
        },
        {
            "model": f"models/{EMBED_MODELS[0]}",
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
        },
        {
            "model": f"models/{EMBED_MODELS[0]}",
            "content": {"parts": [{"text": text}]},
        },
    ]
    model = EMBED_MODELS[0]
    url = f"{GEMINI_BASE}/models/{model}:embedContent"
    errors: list[str] = []
    with _client() as client:
        for body in payloads:
            r = client.post(url, json=body)
            if r.status_code >= 400:
                errors.append(f"HTTP {r.status_code}: {r.text[:160]}")
                if _denied(r.status_code, r.text):
                    _gemini_embed_blocked = True
                    _last_error = "Gemini embeddings denied (403). Using local fallback."
                    raise RuntimeError(_last_error)
                continue
            values = _parse_embedding(r.json())
            if values:
                _working_embed_model = model
                return values
            errors.append("empty embedding")
    raise RuntimeError(" | ".join(errors) or "embed failed")


def _embed_batch_gemini(texts: list[str], task_type: str) -> list[list[float]]:
    global _working_embed_model, _gemini_embed_blocked, _last_error
    if not texts:
        return []
    if len(texts) == 1:
        return [_embed_one_gemini(texts[0], task_type)]

    model = EMBED_MODELS[0]
    url = f"{GEMINI_BASE}/models/{model}:batchEmbedContents"
    out: list[list[float]] = []
    with _client() as client:
        for i in range(0, len(texts), 12):
            batch = texts[i : i + 12]
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
                        for t in batch
                    ]
                },
            )
            if r.status_code >= 400:
                if _denied(r.status_code, r.text):
                    _gemini_embed_blocked = True
                    _last_error = "Gemini embeddings denied (403). Using local fallback."
                    raise RuntimeError(_last_error)
                out.extend(_embed_one_gemini(t, task_type) for t in batch)
                continue
            embs = r.json().get("embeddings") or []
            if len(embs) != len(batch):
                out.extend(_embed_one_gemini(t, task_type) for t in batch)
                continue
            vals = []
            for e in embs:
                if isinstance(e, dict) and e.get("values"):
                    vals.append([float(x) for x in e["values"]])
                else:
                    vals = []
                    break
            if not vals:
                out.extend(_embed_one_gemini(t, task_type) for t in batch)
                continue
            _working_embed_model = model
            out.extend(vals)
    return out


def _embed_docs(texts: list[str]) -> tuple[list[list[float]], str]:
    global _working_embed_model, _gemini_embed_blocked
    s = _settings()
    if s.force_local_rag or not _has_key() or _gemini_embed_blocked:
        _working_embed_model = "local-tfidf"
        return [_local_embed(t) for t in texts], "local"
    try:
        return _embed_batch_gemini(texts, "RETRIEVAL_DOCUMENT"), "gemini"
    except Exception as exc:
        if s.allow_local_fallback:
            _gemini_embed_blocked = True
            _working_embed_model = "local-tfidf"
            return [_local_embed(t) for t in texts], "local"
        raise RuntimeError(str(exc)) from exc


def _embed_query(text: str, mode: str) -> list[float]:
    global _gemini_embed_blocked
    if mode == "local" or not _has_key() or _gemini_embed_blocked or _settings().force_local_rag:
        return _local_embed(text)
    try:
        return _embed_one_gemini(text, "RETRIEVAL_QUERY")
    except Exception:
        if _settings().allow_local_fallback:
            _gemini_embed_blocked = True
            return _local_embed(text)
        raise


def add_document(email: str, filename: str, data: bytes) -> dict:
    text = _extract_text(filename, data)
    pieces = _chunk_text(text)
    if not pieces:
        raise ValueError("No extractable text found in document")

    embeddings, mode = _embed_docs(pieces)
    session = get_session(email)
    session.chunks = [c for c in session.chunks if c.source != filename]
    session.files = [f for f in session.files if f != filename]
    session.files.append(filename)
    session.retrieval_mode = mode
    for piece, emb in zip(pieces, embeddings):
        session.chunks.append(Chunk(text=piece, source=filename, embedding=emb))

    note = "Stored in session memory only — never written to disk or a database."
    if mode == "local":
        note += (
            " Using local retrieval because Gemini embeddings are unavailable "
            "(missing key or 403 project access). Upload still works."
        )

    return {
        "filename": filename,
        "chunks": len(pieces),
        "session_files": list(session.files),
        "embed_model": _working_embed_model or mode,
        "retrieval_mode": mode,
        "note": note,
    }


def list_documents(email: str) -> list[str]:
    return list(get_session(email).files)


def retrieve(email: str, query: str, k: int = TOP_K) -> list[Chunk]:
    session = get_session(email)
    if not session.chunks:
        return []

    sample = next((c.embedding for c in session.chunks if c.embedding), None)
    mode = "local"
    if sample is not None and len(sample) != LOCAL_DIM:
        mode = "gemini"
    elif session.retrieval_mode in {"gemini", "local"}:
        mode = session.retrieval_mode
        if sample is not None and len(sample) == LOCAL_DIM:
            mode = "local"

    q = _embed_query(query, mode)
    if sample is not None and len(q) != len(sample):
        q = _local_embed(query)

    scored = [(_cosine(q, c.embedding), c) for c in session.chunks if c.embedding]
    scored.sort(key=lambda x: x[0], reverse=True)
    hits = [c for _, c in scored[:k]]

    qtoks = set(_tokenize(query))
    if qtoks:
        extra = sorted(
            ((len(qtoks & set(_tokenize(c.text))), c) for c in session.chunks),
            key=lambda x: x[0],
            reverse=True,
        )
        for score, c in extra:
            if score <= 0:
                break
            if c not in hits:
                hits.append(c)
            if len(hits) >= k:
                break
    return hits[:k]


def _generate_gemini(prompt: str) -> str:
    global _working_chat_model, _gemini_chat_blocked, _last_error
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
    }
    errors: list[str] = []
    with _client() as client:
        for model in CHAT_MODELS:
            r = client.post(f"{GEMINI_BASE}/models/{model}:generateContent", json=body)
            if r.status_code >= 400:
                errors.append(f"{model}: HTTP {r.status_code}")
                if _denied(r.status_code, r.text):
                    _gemini_chat_blocked = True
                    _last_error = "Gemini chat denied (403)."
                    raise RuntimeError(_last_error)
                continue
            parts = (
                r.json().get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                _working_chat_model = model
                return text
            errors.append(f"{model}: empty")
    raise RuntimeError(" | ".join(errors) or "generation failed")


def _extractive_answer(question: str, hits: list[Chunk]) -> str:
    qtoks = set(_tokenize(question))
    best = hits[0]
    best_score = -1
    for h in hits:
        score = len(qtoks & set(_tokenize(h.text)))
        if score > best_score:
            best_score = score
            best = h
    sentences = re.split(r"(?<=[.!?])\s+", best.text)
    ranked = []
    for s in sentences:
        s = s.strip()
        if len(s) < 25:
            continue
        ranked.append((len(qtoks & set(_tokenize(s))), s))
    ranked.sort(key=lambda x: x[0], reverse=True)
    picks = [s for sc, s in ranked if sc > 0][:3] or [best.text[:480]]
    sources = ", ".join(sorted({h.source for h in hits}))
    return (
        f"Based on your uploaded documents ({sources}):\n\n"
        + " ".join(picks)
        + "\n\n(Local extractive answer — Gemini chat unavailable for this key/project.)"
    )


def answer_query(email: str, question: str) -> dict:
    hits = retrieve(email, question)
    if not hits:
        return {
            "answer": "No documents in this session yet. Upload a policy file first.",
            "sources": [],
            "session_only": True,
            "retrieval_mode": get_session(email).retrieval_mode,
            "generation_mode": "none",
        }

    context = "\n\n".join(f"[Source: {h.source}]\n{h.text}" for h in hits)
    prompt = f"""You are an enterprise compliance assistant.
Answer ONLY from the policy context below. If missing, say you cannot find it in the uploaded documents.
Be concise and cite source filenames.

Context:
{context}

Question: {question}
"""
    gen_mode = "local"
    if _has_key() and not _gemini_chat_blocked and not _settings().force_local_rag:
        try:
            answer = _generate_gemini(prompt)
            gen_mode = "gemini"
        except Exception:
            if not _settings().allow_local_fallback:
                raise
            answer = _extractive_answer(question, hits)
    else:
        answer = _extractive_answer(question, hits)

    return {
        "answer": answer,
        "sources": sorted({h.source for h in hits}),
        "session_only": True,
        "chat_model": _working_chat_model if gen_mode == "gemini" else "local-extractive",
        "retrieval_mode": get_session(email).retrieval_mode,
        "generation_mode": gen_mode,
        "disclaimer": "Documents exist only in session memory and are never stored permanently.",
    }


def gemini_status() -> dict:
    return {
        "embed_models": list(EMBED_MODELS),
        "chat_models": list(CHAT_MODELS),
        "working_embed_model": _working_embed_model,
        "working_chat_model": _working_chat_model,
        "gemini_configured": _has_key(),
        "gemini_embed_blocked": _gemini_embed_blocked,
        "gemini_chat_blocked": _gemini_chat_blocked,
        "local_fallback_enabled": _settings().allow_local_fallback,
        "force_local_rag": _settings().force_local_rag,
        "last_error": (_last_error or "")[:240],
    }
