"""Offline tests with local fallback (no Gemini key required)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

import rag
from main import app


def main() -> None:
    assert len(rag._chunk_text("word " * 500)) >= 2
    v = rag._local_embed("customer records retained 7 years")
    assert len(v) == rag.LOCAL_DIM

    client = TestClient(app)
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"
    assert h.json().get("local_fallback_enabled") is True

    email = "rebuild@example.com"
    client.post("/api/auth/register", json={"email": email, "password": "secret12", "full_name": "Rebuild"})
    token = client.post("/api/auth/login", data={"username": email, "password": "secret12"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sample = Path(__file__).resolve().parents[1] / "sample_data" / "sample_company_policy.txt"
    up = client.post(
        "/api/documents/upload",
        headers=headers,
        files={"file": ("sample_company_policy.txt", sample.read_bytes(), "text/plain")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["retrieval_mode"] == "local"

    q = client.post(
        "/api/query",
        headers=headers,
        json={"question": "What is the data retention period for customer records?"},
    )
    assert q.status_code == 200, q.text
    body = q.json()
    assert "7 years" in body["answer"].lower()
    assert "sample_company_policy.txt" in body["sources"]
    print("ALL OFFLINE TESTS PASSED")
    print("answer:", body["answer"][:160])


if __name__ == "__main__":
    main()
