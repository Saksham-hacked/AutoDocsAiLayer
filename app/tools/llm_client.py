import asyncio
from google import genai
from google.genai import types
from app.config import get_settings
from app.utils import log

class LLMClient:
    def __init__(self, api_key: str = None, model: str = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model or settings.gemini_llm_model_name
        
        # Create Gemini API client
        self.client = genai.Client(api_key=self.api_key)

    async def complete(self, system: str, user: str, temperature: float = 0.1) -> str:
        """Call Gemini API for text generation."""
        # Combine system and user prompts
        full_prompt = f"{system}\n\n{user}"
        
        # Build generation config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=8192,
        )
        
        for attempt in range(2):
            try:
                # Log the request
                log(
                    node="llm_client",
                    event="request_sent",
                    repo_id="",
                    commit_id="",
                    duration_ms=0,
                    details={"model": self.model_name, "temperature": temperature, "attempt": attempt + 1, "api_key_suffix": self.api_key[-6:]}
                )
                
                # Run synchronous API call in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.models.generate_content(
                        model=self.model_name,
                        contents=full_prompt,
                        config=config
                    )
                )
                
                result = response.text
                
                # Log successful response
                log(
                    node="llm_client",
                    event="response_received",
                    repo_id="",
                    commit_id="",
                    duration_ms=0,
                    details={"model": self.model_name, "response_length": len(result)}
                )
                
                return result
                
            except Exception as e:
                log(
                    node="llm_client",
                    event="error",
                    repo_id="",
                    commit_id="",
                    duration_ms=0,
                    details={"error": str(e), "attempt": attempt + 1}
                )
                
                if attempt == 0:
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError(f"LLM call failed after retry: {e}") from e
        
        return ""
