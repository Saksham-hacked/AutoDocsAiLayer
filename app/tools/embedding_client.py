import httpx
import asyncio
from app.config import get_settings

settings = get_settings()


class EmbeddingClient:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or settings.ollama_api_url
        self.model = model or settings.ollama_embed_model_name

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text via Ollama."""
        url = f"{self.base_url}/api/embeddings"
        payload = {"model": self.model, "prompt": text}
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    return resp.json()["embedding"]
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(f"Embedding failed after retry: {e}") from e
        return []
