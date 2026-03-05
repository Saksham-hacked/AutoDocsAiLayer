# AutoDocs Layer 2 — Setup Guide

## Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Ollama running locally (https://ollama.ai)
- PostgreSQL with pgvector (handled by docker-compose)

## 1. Clone and configure

```bash
git clone <repo>
cd autodocs-layer2
cp .env.example .env
```

Edit `.env` — minimum required changes:

| Variable | What to set |
|---|---|
| `AUTODOCS_SHARED_SECRET` | Any strong secret string shared with Layer1 |
| `OLLAMA_LLM_MODEL_NAME` | Your pulled Ollama model e.g. `mistral`, `llama3` |
| `OLLAMA_EMBED_MODEL_NAME` | Your embedding model e.g. `nomic-embed-text` |
| `OLLAMA_API_URL` | `http://host.docker.internal:11434` when running inside Docker |

## 2. Pull Ollama models (on host)

```bash
ollama pull mistral
ollama pull nomic-embed-text
```

Update `OLLAMA_EMBED_MODEL_NAME=nomic-embed-text` and `EMBEDDING_DIM=768` in `.env` if using nomic-embed-text (768-dim). For 1536-dim models leave `EMBEDDING_DIM=1536`.

## 3. Start with Docker Compose

```bash
cd docker
docker compose up --build
```

Service starts on `http://localhost:8080`. DB schema is applied automatically on first start via `docker-entrypoint-initdb.d`.

## 4. Verify

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

## 5. Run locally without Docker

```bash
pip install -r requirements.txt
# Start Postgres+pgvector separately, then:
export $(cat .env | xargs)
psql $PG_DSN -f app/schema/create_tables.sql
bash scripts/run_local.sh
```

## 6. Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## 7. Enable LangSmith tracing (optional)

Set in `.env`:
```
ENABLE_LANGSMITH=true
LANGSMITH_API_KEY=ls__your_key
```

Get API key at https://smith.langchain.com

## File reference

### Entry points

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app factory — imports router and mounts it |
| `app/api.py` | Route handlers: `POST /process-change` and `GET /health`; validates shared secret |
| `app/langgraph_graph.py` | Builds and compiles the LangGraph `StateGraph`; wires all 7 nodes in order |
| `app/config.py` | Pydantic-settings config loader; reads `.env`; cached singleton via `get_settings()` |
| `app/models.py` | All Pydantic models: `ProcessChangeRequest`, `ProcessChangeResponse`, `GraphState`, `FileUpdate`, `SourceRef` |
| `app/utils.py` | Shared helpers: marker extract/replace, `parse_llm_json`, `build_repo_id`, structured JSON logger |
| `app/observability.py` | LangSmith trace context manager (`trace_node`); no-op when `ENABLE_LANGSMITH=false` |
| `app/scaffold.py` | `scaffold_docs()` — returns patch list of stub doc files with empty AUTODOCS markers for new repos |

### Agents (LangGraph nodes)

| File | Node | What it does |
|---|---|---|
| `app/agents/classify_change.py` | `validate_input` | Validates request fields, sets `repo_id`, skips pipeline if `changedFiles` empty |
| `app/agents/update_memory.py` | `update_memory` | Fetches each changed file from Layer1, LLM-summarises it, embeds the summary, upserts to pgvector |
| `app/agents/retrieve_context.py` | `retrieve_context` | Builds query from diffs + changed summaries, embeds it, runs top-K retrieval; falls back gracefully on embed failure |
| `app/agents/impact_analysis.py` | `impact_analysis` | Rule-based pre-check + LLM classification → change labels + relevance score; sets `skip_generation` if score < threshold |
| `app/agents/generate_docs.py` | `generate_docs` | For each target doc: fetches existing file, extracts marker, calls LLM with style guide, parses JSON response into `FileUpdate` |
| `app/agents/confidence.py` | `confidence_check` | Downgrades confidence if any file has `UNVERIFIED` markers; sets `overall_confidence`; flags `review_required` in PR body |
| `app/agents/format_response.py` | `format_response` | Assembles final `pr_title` and `pr_body`; returns no-update response if `skip_generation` is set |

### Tools

| File | Purpose |
|---|---|
| `app/tools/layer1_client.py` | `Layer1Client` — async httpx client for `fetch_file`, `fetch_diff`, `patch_files`; always sends `X-AUTODOCS-SECRET` header |
| `app/tools/llm_client.py` | `LLMClient` — calls Ollama `/api/chat`; temperature ≤ 0.2; 1 retry with backoff |
| `app/tools/embedding_client.py` | `EmbeddingClient` — calls Ollama `/api/embeddings`; 1 retry with backoff |
| `app/tools/vectorstore.py` | `upsert_summary`, `delete_summary`, `retrieve_top_k` — asyncpg-backed pgvector helpers |

### Prompts

| File | Used by | Content |
|---|---|---|
| `app/prompts/summarize_file.prompt.txt` | `update_memory` | System prompt for 150-200 word file summary |
| `app/prompts/classify_change.prompt.txt` | `impact_analysis` | System prompt for JSON label + relevance score output |
| `app/prompts/generate_doc_update.prompt.txt` | `generate_docs` | Full style guide + JSON output contract for doc section generation |

### Schema

| File | Purpose |
|---|---|
| `app/schema/create_tables.sql` | Creates `summaries` table with `vector` column + ivfflat index; mounted into Postgres container on first run |

### Tests

| File | Type | Covers |
|---|---|---|
| `tests/unit/test_utils.py` | Unit | Marker extract/replace, `parse_llm_json` with and without fences |
| `tests/unit/test_validate.py` | Unit | `validate_input` node: repo_id set correctly, empty files triggers skip |
| `tests/unit/test_api_auth.py` | Unit | Missing secret → 401, wrong secret → 401, health → 200 |
| `tests/integration/test_flow.py` | Integration | Full mocked pipeline for new GET /settings route; embedding fallback resilience |
| `tests/fixtures/new_route_payload.json` | Fixture | Sample `POST /process-change` request payload |
| `tests/fixtures/settings.js` | Fixture | Sample source file used as Layer1 fetch response in tests |

### Docker & scripts

| File | Purpose |
|---|---|
| `docker/Dockerfile` | Python 3.11 slim image; installs requirements; runs uvicorn on port 8080 |
| `docker/docker-compose.yml` | Starts `db` (ankane/pgvector) + `autodocs` service; mounts SQL schema for auto-init |
| `scripts/init_db.sh` | Runs `create_tables.sql` against `$PG_DSN` — use for manual DB init |
| `scripts/run_local.sh` | Copies `.env.example` if no `.env` exists, then starts uvicorn with `--reload` |
| `scripts/run_tests.sh` | Runs `pytest tests/ -v` |
| `simulate_commit.py` | CLI smoke-test: posts a fixture payload to the running service and prints the response |

---

## Local run & testing guide

### Step 1 — Install Python dependencies

```bash
cd autodocs-layer2
pip install -r requirements.txt
```

### Step 2 — Configure environment

```bash
cp .env.example .env
```

Minimum edits in `.env` before running locally:

```
AUTODOCS_SHARED_SECRET=changeme
OLLAMA_LLM_MODEL_NAME=mistral          # must match a pulled Ollama model
OLLAMA_EMBED_MODEL_NAME=nomic-embed-text  # must match a pulled Ollama model
EMBEDDING_DIM=768                      # 768 for nomic-embed-text, 1536 for others
OLLAMA_API_URL=http://localhost:11434
PG_DSN=postgresql://user:pass@localhost:5432/autodocs
```

### Step 3 — Start Ollama and pull models (host machine)

```bash
# Install Ollama from https://ollama.ai then:
ollama pull mistral
ollama pull nomic-embed-text
```

Verify Ollama is running:

```bash
curl http://localhost:11434/api/tags
```

### Step 4 — Start Postgres with pgvector

Option A — Docker only for DB (recommended for local dev):

```bash
docker run -d \
  --name autodocs-pg \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=pass \
  -e POSTGRES_DB=autodocs \
  -p 5432:5432 \
  ankane/pgvector:latest
```

Option B — Full docker-compose (DB + service together):

```bash
cd docker
docker compose up --build
# Service available at http://localhost:8080 — skip steps 5 and 6
```

### Step 5 — Initialise the database schema

```bash
export PG_DSN=postgresql://user:pass@localhost:5432/autodocs
psql $PG_DSN -f app/schema/create_tables.sql
```

Expected output: `CREATE TABLE`, `CREATE INDEX` (no errors).

### Step 6 — Start the service

```bash
bash scripts/run_local.sh
# or directly:
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Verify it's up:

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

---

### Running the test suite

#### All tests

```bash
pytest tests/ -v
```

#### Unit tests only (no DB or Ollama needed)

```bash
pytest tests/unit/ -v
```

#### Integration tests only

```bash
pytest tests/integration/ -v
```

Integration tests mock Layer1, Ollama, and the vector store — no live services required.

#### Run a single test file

```bash
pytest tests/unit/test_utils.py -v
pytest tests/integration/test_flow.py::test_full_new_route_flow -v
```

#### Expected passing tests

| Test | What it checks |
|---|---|
| `test_utils.py::test_marker_extraction` | Extracts content between AUTODOCS marker tags |
| `test_utils.py::test_marker_replacement` | Replaces marker content, preserves surrounding text |
| `test_utils.py::test_marker_insert_when_missing` | Inserts new marker block when none exists |
| `test_utils.py::test_parse_llm_json_clean` | Parses plain JSON from LLM output |
| `test_utils.py::test_parse_llm_json_with_fences` | Strips markdown fences before parsing |
| `test_validate.py::test_validate_input_sets_repo_id` | Sets `repo_id` as `owner/repo` |
| `test_validate.py::test_validate_input_empty_files` | Sets `skip_generation=True` for empty changedFiles |
| `test_api_auth.py::test_health` | `/health` returns 200 |
| `test_api_auth.py::test_missing_secret` | Missing header returns 401 |
| `test_api_auth.py::test_wrong_secret` | Wrong secret returns 401 |
| `test_flow.py::test_full_new_route_flow` | Full pipeline returns `docs/api.md` update with PR title |
| `test_flow.py::test_retrieval_fallback_on_embed_error` | Embed failure doesn't crash; returns 200 |

---

### Manual end-to-end smoke test

With the service running on port 8080:

```bash
python simulate_commit.py tests/fixtures/new_route_payload.json
```

Expected response shape:

```json
{
  "files_to_update": [
    {
      "path": "docs/api.md",
      "content": "...",
      "confidence": "High",
      "sources": [{"path": "src/routes/settings.js", "lines": "1-12", "score": 0.95}]
    }
  ],
  "pr_title": "📝 AutoDocs: NEW_API_ROUTE (abc1234)",
  "pr_body": "...",
  "confidence": "High"
}
```

Or send manually with curl:

```bash
curl -s -X POST http://localhost:8080/process-change \
  -H "Content-Type: application/json" \
  -H "X-AUTODOCS-SECRET: changeme" \
  -d @tests/fixtures/new_route_payload.json | python -m json.tool
```

### Checking structured logs

The service emits JSON logs to stdout. Each log line contains `timestamp`, `repo_id`, `commit_id`, `node`, `event`, `duration_ms`. Filter by node:

```bash
# if running with docker compose:
docker compose logs autodocs -f | grep '"node"'

# locally: logs go to stdout directly
```

### Common local issues

| Symptom | Fix |
|---|---|
| `connection refused` on port 5432 | Postgres container not running — run Step 4 |
| `vector type does not exist` | `create_tables.sql` not applied — run Step 5 |
| `embed failed after retry` | Ollama not running or wrong model name in `.env` |
| `LLM call failed after retry` | Ollama not running or `OLLAMA_LLM_MODEL_NAME` not pulled |
| 401 on all requests | `AUTODOCS_SHARED_SECRET` in `.env` doesn't match header used |
| Tests fail with `ModuleNotFoundError` | Run `pip install -r requirements.txt` from repo root |

---

## Environment variable reference

| Variable | Default | Description |
|---|---|---|
| `AUTODOCS_SHARED_SECRET` | `changeme` | Shared secret for X-AUTODOCS-SECRET header |
| `OLLAMA_API_URL` | `http://localhost:11434` | Ollama API base URL |
| `OLLAMA_LLM_MODEL_NAME` | `mistral` | Ollama LLM model name |
| `OLLAMA_EMBED_MODEL_NAME` | `embed-model` | Ollama embedding model name |
| `PG_DSN` | — | Postgres connection string |
| `EMBEDDING_DIM` | `1536` | Embedding vector dimension (must match model) |
| `RETRIEVAL_K` | `5` | Top-K results to retrieve from vector store |
| `RELEVANCE_THRESHOLD` | `70` | Min relevance score (0-100) to trigger doc generation |
| `ENABLE_LANGSMITH` | `false` | Enable LangSmith tracing |
| `LANGSMITH_API_KEY` | — | LangSmith API key |
| `LAYER1_BASE_URL` | `http://localhost:8000` | Layer1 service base URL |
| `LOG_LEVEL` | `info` | Logging level |
