"""Offline tests — no Gemini key required."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
import rag
from main import app


def test_chunk_and_extract():
    text = ("Customer account records are retained for 7 years after account closure. " * 40).strip()
    chunks = rag._chunk_text(text)
    assert len(chunks) >= 2
    extracted = rag._extract_text("policy.txt", text.encode("utf-8"))
    assert "7 years" in extracted
    print("chunk/extract OK", len(chunks), "chunks")


def test_cosine():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    c = [0.0, 1.0, 0.0]
    assert abs(rag._cosine(a, b) - 1.0) < 1e-6
    assert abs(rag._cosine(a, c)) < 1e-6
    print("cosine OK")


def test_auth_and_health():
    client = TestClient(app)
    h = client.get("/api/health")
    assert h.status_code == 200
    body = h.json()
    assert body["status"] == "ok"
    assert "gemini-embedding-001" in body.get("embed_models", [])
    assert "embedding-001" not in body.get("embed_models", [])

    r = client.post(
        "/api/auth/register",
        json={"email": "test@example.com", "password": "secret12", "full_name": "Tester"},
    )
    assert r.status_code == 200, r.text

    login = client.post(
        "/api/auth/login",
        data={"username": "test@example.com", "password": "secret12"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"
    print("auth/health OK")


def test_upload_requires_gemini_or_mocks():
    """Without a key, upload should return a clear 503, not a 500 crash."""
    client = TestClient(app)
    client.post(
        "/api/auth/register",
        json={"email": "nokey@example.com", "password": "secret12", "full_name": "NoKey"},
    )
    login = client.post(
        "/api/auth/login",
        data={"username": "nokey@example.com", "password": "secret12"},
    )
    token = login.json()["access_token"]
    files = {"file": ("policy.txt", b"Retention is 7 years.", "text/plain")}
    res = client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
    )
    # Either works (if key present) or clean 503
    assert res.status_code in (200, 503), res.text
    if res.status_code == 503:
        assert "GEMINI" in res.json()["detail"].upper() or "Embedding" in res.json()["detail"]
        print("upload without key returns clean 503 OK")
    else:
        print("upload with key OK", res.json())


if __name__ == "__main__":
    test_chunk_and_extract()
    test_cosine()
    test_auth_and_health()
    test_upload_requires_gemini_or_mocks()
    print("ALL OFFLINE TESTS PASSED")
