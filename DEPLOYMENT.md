# AutoDocs Layer 2 — Deployment Guide

## Production deployment (Docker)

### 1. Build image

```bash
docker build -f docker/Dockerfile -t autodocs-layer2:latest .
```

### 2. Required environment variables in production

Set these as secrets/env vars in your platform — never commit them:

```
AUTODOCS_SHARED_SECRET=<strong-random-secret>
OLLAMA_API_URL=<your-ollama-host>
OLLAMA_LLM_MODEL_NAME=mistral
OLLAMA_EMBED_MODEL_NAME=nomic-embed-text
PG_DSN=postgresql://user:pass@<pg-host>:5432/autodocs
EMBEDDING_DIM=768
ENABLE_LANGSMITH=true
LANGSMITH_API_KEY=<key>
```

### 3. Database setup

Run once on your production Postgres (must have pgvector extension):

```bash
psql $PG_DSN -f app/schema/create_tables.sql
```

pgvector must be installed on your Postgres server. For managed Postgres:
- **Supabase**: pgvector enabled by default
- **AWS RDS**: enable via `CREATE EXTENSION vector;`
- **Neon**: pgvector available, run `CREATE EXTENSION vector;`

### 4. Run container

```bash
docker run -d \
  --name autodocs-layer2 \
  -p 8080:8080 \
  --env-file .env \
  autodocs-layer2:latest
```

### 5. Docker Compose (full stack local/staging)

```bash
cd docker
docker compose up -d
```

Note: Ollama is expected to run on the host. Set `OLLAMA_API_URL=http://host.docker.internal:11434` in `.env` when running the service in Docker with Ollama on the host machine.

## Deploying to a cloud platform

### Railway / Render / Fly.io

1. Push the repo.
2. Set env vars in the platform dashboard.
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Provision a Postgres addon with pgvector support.
6. Run schema migration manually once.

### Kubernetes

Create a Deployment with:
- Image: `autodocs-layer2:latest`
- Env from a Secret containing all variables above
- LivenessProbe: `GET /health`
- Port: `8080`

## Scaling considerations

- The service is stateless; scale horizontally freely.
- The DB (pgvector) is the only stateful component.
- For large repos, increase `RETRIEVAL_K` and `RELEVANCE_THRESHOLD` as needed.
- LLM calls are the main latency bottleneck — use a faster/local Ollama model or GPU-backed instance.

## How Layer1 calls this service

```
POST /process-change
Header: X-AUTODOCS-SECRET: <shared-secret>
Content-Type: application/json

Body: see SETUP.md or models.py ProcessChangeRequest
```

Response contains `files_to_update[]` with path, content, confidence, and sources. Layer1 is responsible for opening the PR.

## Simulate a commit (smoke test)

```bash
python simulate_commit.py tests/fixtures/new_route_payload.json
```

## Scaffold docs for a new repo

Call the scaffold utility from Python or add a `/scaffold` endpoint:

```python
from app.scaffold import scaffold_docs
patches = scaffold_docs("owner/repo", "owner", "main")
# Send patches to Layer1 apply-patch endpoint
```

## Troubleshooting

| Problem | Fix |
|---|---|
| 401 on all requests | Check `AUTODOCS_SHARED_SECRET` matches between Layer1 and this service |
| Embedding errors | Verify Ollama is running and `OLLAMA_EMBED_MODEL_NAME` is pulled |
| `vector` type errors in PG | Run `CREATE EXTENSION vector;` in your DB |
| LLM returns non-JSON | Increase `RELEVANCE_THRESHOLD` or improve your Ollama model |
| LangSmith traces missing | Set `ENABLE_LANGSMITH=true` and verify `LANGSMITH_API_KEY` |
