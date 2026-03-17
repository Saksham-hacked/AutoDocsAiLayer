# Migration from Ollama to Gemini API - CORRECTED

## ✅ Migration Complete (Using NEW Google GenAI SDK)

**IMPORTANT**: This migration uses the **new unified `google-genai` package**, NOT the deprecated `google-generativeai` package.

## Changes Made

### 1. Updated Configuration (`app/config.py`)
- Replaced Ollama-specific settings with Gemini API settings
- Changed `ollama_api_url` → Removed (not needed for Gemini)
- Changed `ollama_llm_model_name` → `gemini_llm_model_name` (default: `gemini-1.5-flash`)
- Changed `ollama_embed_model_name` → `gemini_embed_model_name` (default: `models/text-embedding-004`)
- Added `gemini_api_key` for API authentication
- Updated `embedding_dim` default to 768 (matches text-embedding-004)

### 2. Rewrote LLM Client (`app/tools/llm_client.py`)
- **Uses NEW `google-genai` package** (NOT deprecated `google-generativeai`)
- Import: `from google import genai` ✅
- Uses `genai.Client(api_key=...)` for client creation
- Uses `client.models.generate_content()` for text generation
- Combines system and user prompts (Gemini doesn't have separate system role)
- Maintained same retry logic (2 attempts with 2-second delay)
- **Added detailed logging** for all requests, responses, and errors
- Wrapped synchronous API calls in `asyncio.run_in_executor` for non-blocking execution

### 3. Rewrote Embedding Client (`app/tools/embedding_client.py`)
- **Uses NEW `google-genai` package** (NOT deprecated `google-generativeai`)
- Import: `from google import genai` ✅
- Uses `genai.Client(api_key=...)` for client creation
- Uses `client.models.embed_content()` for embeddings
- Extracts embedding from `response.embeddings[0].values`
- Maintained same retry logic (2 attempts with 1-second delay)
- **Added detailed logging** for all requests, responses, and errors
- Wrapped synchronous API calls in `asyncio.run_in_executor` for non-blocking execution

### 4. Updated Dependencies (`requirements.txt`)
- Added `google-genai>=1.0.0` ✅ (NEW unified SDK)
- **NOT** using deprecated `google-generativeai` ❌

### 5. Updated Environment Template (`.env.example`)
- Replaced all Ollama variables with Gemini equivalents
- Added clear section headers for better organization
- Updated comments and defaults

## Package Information

### ✅ CORRECT (What we're using):
```bash
pip install google-genai
```
```python
from google import genai
client = genai.Client(api_key='...')
```

### ❌ WRONG (Deprecated, do NOT use):
```bash
pip install google-generativeai  # DEPRECATED!
```
```python
import google.generativeai as genai  # OLD/DEPRECATED!
```

## What Was NOT Changed

✅ **All logging functionality preserved** - Logs still output to stdout as JSON
✅ **No changes to agent nodes** - All 7 LangGraph nodes untouched
✅ **No changes to API endpoints** - FastAPI routes remain identical
✅ **No changes to database schema** - Vector store logic unchanged
✅ **No changes to prompts** - All prompt templates remain the same
✅ **No changes to utilities** - `utils.py`, `observability.py` untouched
✅ **No changes to tests** - Test files remain compatible
✅ **No changes to Docker setup** - Dockerfile and docker-compose.yml unchanged

## Setup Instructions

### 1. Get Gemini API Key
1. Go to https://aistudio.google.com/app/apikey
2. Create a new API key
3. Copy the key

### 2. Update Environment Variables
Edit your `.env` file (or create from `.env.example`):

```bash
cp .env.example .env
```

Then update:
```env
GEMINI_API_KEY=your_actual_api_key_here
GEMINI_LLM_MODEL_NAME=gemini-1.5-flash  # or gemini-1.5-pro, gemini-2.5-flash
GEMINI_EMBED_MODEL_NAME=models/text-embedding-004
EMBEDDING_DIM=768  # CRITICAL: Must match embedding model output
```

### 3. Install New Dependencies
```bash
pip install -r requirements.txt
```

This will install `google-genai` (the NEW unified SDK).

Or if using Docker:
```bash
cd docker
docker compose build
docker compose up
```

### 4. Update Database (if needed)
If you were using a different `EMBEDDING_DIM` before (e.g., 1536 for Ollama models), you need to:

**Option A - Fresh start (recommended for testing):**
```bash
# Drop and recreate the table
psql $PG_DSN -c "DROP TABLE IF EXISTS summaries;"
psql $PG_DSN -f app/schema/create_tables.sql
```

**Option B - Keep existing data (requires manual migration):**
```sql
-- You'll need to re-embed all summaries with the new model
-- This is complex and may require custom migration script
```

### 5. Verify Setup
```bash
# Start the service
bash scripts/run_local.sh

# In another terminal, check health
curl http://localhost:8080/health

# Run a test
python simulate_commit.py tests/fixtures/new_route_payload.json
```

## Gemini Model Options

### LLM Models (for text generation):
- `gemini-1.5-flash` - Fast, cost-effective (recommended for development)
- `gemini-1.5-pro` - Higher quality, slower, more expensive (recommended for production)
- `gemini-2.5-flash` - Latest experimental version
- `gemini-2.5-pro` - Highest quality available

### Embedding Models:
- `models/text-embedding-004` - 768 dimensions (recommended) ✅
- `models/embedding-001` - 768 dimensions (older)

## Logging Verification

All logs are still output as JSON to stdout. You'll now see:

```json
{"timestamp": "...", "node": "llm_client", "event": "request_sent", "details": {"model": "gemini-1.5-flash", "temperature": 0.1, "attempt": 1}}
{"timestamp": "...", "node": "llm_client", "event": "response_received", "details": {"model": "gemini-1.5-flash", "response_length": 1234}}
{"timestamp": "...", "node": "embedding_client", "event": "request_sent", "details": {"model": "models/text-embedding-004", "text_length": 456, "attempt": 1}}
{"timestamp": "...", "node": "embedding_client", "event": "response_received", "details": {"model": "models/text-embedding-004", "embedding_dim": 768}}
```

To view logs in real-time:
```bash
# If running with docker-compose
docker compose logs autodocs -f

# If running locally
# Logs go directly to stdout
```

## Cost Considerations

Gemini API pricing (as of 2024):

- **gemini-1.5-flash**: $0.075 per 1M input tokens, $0.30 per 1M output tokens
- **gemini-1.5-pro**: $1.25 per 1M input tokens, $5.00 per 1M output tokens  
- **text-embedding-004**: $0.00001 per 1K characters (extremely cheap)

For a typical commit with 5 files:
- ~5 embedding calls: < $0.001
- ~3 LLM calls: ~$0.01-0.05
- Total: **< $0.10 per commit**

## Troubleshooting

### Error: "API key not found"
- Verify `GEMINI_API_KEY` is set in `.env`
- Make sure `.env` file is in the project root
- Check the API key is valid at https://aistudio.google.com/app/apikey

### Error: "Embedding dimension mismatch"
- Ensure `EMBEDDING_DIM=768` in `.env`
- Drop and recreate the `summaries` table (see step 4 above)

### Error: "Rate limit exceeded"
- Gemini free tier: 15 requests per minute
- Gemini paid tier: 1000 requests per minute
- Add delays between requests if hitting limits

### Error: Module not found: google.genai
- Make sure you installed `google-genai` (NOT `google-generativeai`)
- Run: `pip install google-genai`
- Verify: `pip list | grep google-genai`

### Logs not appearing
- Check `LOG_LEVEL` in `.env` (should be `info` or `debug`)
- Verify the service is actually running
- If using Docker, check `docker compose logs autodocs`

## Migration from Deprecated Package

If you previously installed the deprecated `google-generativeai`:

```bash
# Uninstall old package
pip uninstall google-generativeai

# Install new package
pip install google-genai
```

## References

- **Official Docs**: https://googleapis.github.io/python-genai/
- **GitHub Repo**: https://github.com/googleapis/python-genai
- **Gemini API Docs**: https://ai.google.dev/gemini-api/docs
- **Deprecation Notice**: https://github.com/google-gemini/deprecated-generative-ai-python

## Rollback Instructions

If you need to rollback to Ollama:

1. Restore old files from git:
```bash
git checkout HEAD -- app/config.py app/tools/llm_client.py app/tools/embedding_client.py requirements.txt .env.example
```

2. Update `.env` back to Ollama settings
3. Reinstall dependencies: `pip install -r requirements.txt`
4. Restart the service
