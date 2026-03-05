import httpx
import asyncio
from app.config import get_settings

settings = get_settings()


class LLMClient:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or settings.ollama_api_url
        self.model = model or settings.ollama_llm_model_name

    async def complete(self, system: str, user: str, temperature: float = 0.1) -> str:
        """Call Ollama chat completion endpoint."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    return resp.json()["message"]["content"]
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(f"LLM call failed after retry: {e}") from e
        return ""
