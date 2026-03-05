import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

SECRET = "changeme"


@pytest.fixture
def payload():
    with open("tests/fixtures/new_route_payload.json") as f:
        return json.load(f)


def test_full_new_route_flow(payload):
    """Integration test: simulate new GET /settings route commit."""
    with patch("app.tools.layer1_client.Layer1Client.fetch_file", new_callable=AsyncMock) as mock_fetch, \
         patch("app.tools.llm_client.LLMClient.complete", new_callable=AsyncMock) as mock_llm, \
         patch("app.tools.embedding_client.EmbeddingClient.embed", new_callable=AsyncMock) as mock_embed, \
         patch("app.tools.vectorstore.upsert_summary", new_callable=AsyncMock), \
         patch("app.tools.vectorstore.retrieve_top_k", new_callable=AsyncMock) as mock_retrieve:

        mock_fetch.return_value = open("tests/fixtures/settings.js").read()
        mock_embed.return_value = [0.1] * 1536
        mock_retrieve.return_value = []

        # LLM responses: summarize -> classify -> generate
        mock_llm.side_effect = [
            "This module exports a GET /settings route using Express Router. It calls getSettings() and returns JSON.",
            '{"labels": ["NEW_API_ROUTE"], "relevance_score": 90, "reasoning": "adds route"}',
            '{"content": "## GET /settings\\nReturns application settings.\\n\\nSOURCE: src/routes/settings.js:1-12\\nCONFIDENCE: High", "confidence": "High", "sources": [{"path": "src/routes/settings.js", "lines": "1-12", "score": 0.95}]}',
        ]

        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        r = client.post("/process-change", json=payload, headers={"X-AUTODOCS-SECRET": SECRET})
        assert r.status_code == 200
        data = r.json()
        assert len(data["files_to_update"]) > 0
        assert "api.md" in data["files_to_update"][0]["path"]
        assert data["pr_title"] is not None


def test_retrieval_fallback_on_embed_error(payload):
    """If embedding fails, should still return a response without crashing."""
    with patch("app.tools.layer1_client.Layer1Client.fetch_file", new_callable=AsyncMock) as mock_fetch, \
         patch("app.tools.llm_client.LLMClient.complete", new_callable=AsyncMock) as mock_llm, \
         patch("app.tools.embedding_client.EmbeddingClient.embed", new_callable=AsyncMock) as mock_embed, \
         patch("app.tools.vectorstore.upsert_summary", new_callable=AsyncMock), \
         patch("app.tools.vectorstore.retrieve_top_k", new_callable=AsyncMock):

        mock_fetch.return_value = "some code"
        mock_embed.side_effect = RuntimeError("embed failed")
        mock_llm.side_effect = [
            "Summary of file.",
            '{"labels": ["NEW_API_ROUTE"], "relevance_score": 90, "reasoning": "adds route"}',
            '{"content": "## GET /settings", "confidence": "Medium", "sources": []}',
        ]

        from app.main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        r = client.post("/process-change", json=payload, headers={"X-AUTODOCS-SECRET": SECRET})
        assert r.status_code == 200
