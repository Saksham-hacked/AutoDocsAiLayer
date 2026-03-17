import asyncio
from google import genai
from google.genai import types
from app.config import get_settings
from app.utils import log

class EmbeddingClient:
    def __init__(self, api_key: str = None, model: str = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.embedding_dim = settings.embedding_dim
        # Strip 'models/' prefix — new SDK uses bare model name e.g. 'text-embedding-004'
        raw = model or settings.gemini_embed_model_name
        self.model_name = raw.replace("models/", "")
        
        # Create Gemini API client
        self.client = genai.Client(api_key=self.api_key)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for text via Gemini API."""
        for attempt in range(2):
            try:
                # Log the request
                log(
                    node="embedding_client",
                    event="request_sent",
                    repo_id="",
                    commit_id="",
                    duration_ms=0,
                    details={"model": self.model_name, "text_length": len(text), "attempt": attempt + 1}
                )
                
                # Run synchronous API call in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                
                config = types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=self.embedding_dim
                )
                
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.models.embed_content(
                        model=self.model_name,
                        contents=text,
                        config=config
                    )
                )
                
                # Extract embedding from response
                embedding = response.embeddings[0].values
                
                # Log successful response
                log(
                    node="embedding_client",
                    event="response_received",
                    repo_id="",
                    commit_id="",
                    duration_ms=0,
                    details={"model": self.model_name, "embedding_dim": len(embedding)}
                )
                
                return embedding
                
            except Exception as e:
                log(
                    node="embedding_client",
                    event="error",
                    repo_id="",
                    commit_id="",
                    duration_ms=0,
                    details={"error": str(e), "attempt": attempt + 1}
                )
                
                if attempt == 0:
                    await asyncio.sleep(1)
                else:
                    raise RuntimeError(f"Embedding failed after retry: {e}") from e
        
        return []
