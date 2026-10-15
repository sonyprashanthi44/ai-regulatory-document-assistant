"""Full RAG path with mocked Gemini HTTP — no real API key needed."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rag
from fastapi.testclient import TestClient
from main import app


def _fake_embedding(dim: int = 8, seed: float = 0.1) -> list[float]:
    # deterministic pseudo vector from seed
    return [((seed * (i + 1) * 17) % 1.0) - 0.5 for i in range(dim)]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url: str, json=None, params=None, **kwargs):
        body = json or {}
        if ":batchEmbedContents" in url:
            reqs = body.get("requests") or []
            embs = []
            for i, req in enumerate(reqs):
                text = req["content"]["parts"][0]["text"]
                seed = (sum(ord(c) for c in text) % 100) / 100.0
                embs.append({"values": _fake_embedding(8, seed)})
            return FakeResponse(200, {"embeddings": embs})
        if ":embedContent" in url:
            text = body["content"]["parts"][0]["text"]
            seed = (sum(ord(c) for c in text) % 100) / 100.0
            return FakeResponse(200, {"embedding": {"values": _fake_embedding(8, seed)}})
        if ":generateContent" in url:
            return FakeResponse(
                200,
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            "Customer account records are retained for 7 years "
                                            "after account closure (sample_company_policy.txt)."
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return FakeResponse(404, {"error": f"unexpected url {url}"})


def test_mocked_upload_and_query():
    sample = Path(__file__).resolve().parents[1] / "sample_data" / "sample_company_policy.txt"
    data = sample.read_bytes()

    with patch.object(rag, "_api_key", return_value="test-key"), patch(
        "httpx.Client", FakeClient
    ), patch.object(rag, "get_settings") if False else patch(
        "config.get_settings"
    ) as gs:
        # ensure settings resolves key
        mock_settings = MagicMock()
        mock_settings.resolved_gemini_key.return_value = "test-key"
        mock_settings.origins = ["*"]
        mock_settings.secret_key = "test-secret"
        mock_settings.algorithm = "HS256"
        mock_settings.access_token_expire_minutes = 60
        gs.return_value = mock_settings

        # direct rag functions
        rag.clear_session("mock@example.com")
        result = rag.add_document("mock@example.com", "sample_company_policy.txt", data)
        assert result["chunks"] >= 1
        assert result["filename"] == "sample_company_policy.txt"
        assert rag._working_embed_model is not None

        ans = rag.answer_query(
            "mock@example.com",
            "What is the data retention period for customer records?",
        )
        assert "7 years" in ans["answer"]
        assert "sample_company_policy.txt" in ans["sources"]
        print("mocked rag OK", result["chunks"], "chunks; answer:", ans["answer"][:80])

    # HTTP API path
    with patch.object(rag, "_api_key", return_value="test-key"), patch("httpx.Client", FakeClient):
        client = TestClient(app)
        client.post(
            "/api/auth/register",
            json={"email": "mockapi@example.com", "password": "secret12", "full_name": "Mock"},
        )
        token = client.post(
            "/api/auth/login",
            data={"username": "mockapi@example.com", "password": "secret12"},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        up = client.post(
            "/api/documents/upload",
            headers=headers,
            files={"file": ("sample_company_policy.txt", data, "text/plain")},
        )
        assert up.status_code == 200, up.text
        q = client.post(
            "/api/query",
            headers=headers,
            json={"question": "How long are customer account records retained?"},
        )
        assert q.status_code == 200, q.text
        body = q.json()
        assert "7 years" in body["answer"]
        print("mocked HTTP API OK")


if __name__ == "__main__":
    test_mocked_upload_and_query()
    print("ALL MOCK RAG TESTS PASSED")
