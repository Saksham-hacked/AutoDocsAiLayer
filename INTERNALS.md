# AutoDocs Layer 2 — Complete Internals Reference

Everything inside out: every function, every data shape, every data flow, every decision point.

---

## Table of Contents

1. [What this service does in one paragraph](#1-what-this-service-does-in-one-paragraph)
2. [Big picture: how a commit becomes a doc update](#2-big-picture-how-a-commit-becomes-a-doc-update)
3. [Data shapes that flow through the system](#3-data-shapes-that-flow-through-the-system)
4. [Entry point: API layer](#4-entry-point-api-layer)
5. [The LangGraph pipeline](#5-the-langgraph-pipeline)
6. [Node 1 — validate_input](#6-node-1--validate_input)
7. [Node 2 — update_memory](#7-node-2--update_memory)
8. [Node 3 — retrieve_context](#8-node-3--retrieve_context)
9. [Node 4 — impact_analysis](#9-node-4--impact_analysis)
10. [Node 5 — generate_docs](#10-node-5--generate_docs)
11. [Node 6 — confidence_check](#11-node-6--confidence_check)
12. [Node 7 — format_response](#12-node-7--format_response)
13. [Tools in depth](#13-tools-in-depth)
14. [Utilities in depth](#14-utilities-in-depth)
15. [Prompts in depth](#15-prompts-in-depth)
16. [Database schema and vector store](#16-database-schema-and-vector-store)
17. [Observability layer](#17-observability-layer)
18. [Scaffold utility](#18-scaffold-utility)
19. [The skip_generation fast-exit flag](#19-the-skip_generation-fast-exit-flag)
20. [Full data flow trace for a real commit](#20-full-data-flow-trace-for-a-real-commit)
21. [Error handling and resilience map](#21-error-handling-and-resilience-map)
22. [Config and how every setting is used](#22-config-and-how-every-setting-is-used)

---

## 1. What this service does in one paragraph

Layer 2 receives a webhook-like payload from Layer 1 (the GitHub integration layer) whenever code is pushed. It reads the changed files, summarises them with a local LLM (Ollama), stores those summaries as vector embeddings in Postgres, retrieves the most semantically related summaries it already knows about, decides which documentation files need to be updated, generates the new documentation content using the LLM, and returns a structured JSON response telling Layer 1 exactly what text to write into which doc files — along with a suggested PR title and confidence level. Layer 1 then opens the actual GitHub PR. Layer 2 never touches GitHub directly.

---

## 2. Big picture: how a commit becomes a doc update

```
Layer 1 (GitHub integration)
        │
        │  POST /process-change
        │  Header: X-AUTODOCS-SECRET
        │  Body: repo, owner, branch, changedFiles, diffs, commitId ...
        ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI  (api.py)                   │
│  1. Validate shared secret                          │
│  2. Build initial GraphState                        │
│  3. Call graph.ainvoke(state)                       │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              LangGraph StateGraph                    │
│                                                     │
│  validate_input                                     │
│       │                                             │
│  update_memory  ◄── Layer1Client (fetch files)      │
│       │         ◄── LLMClient    (summarise)        │
│       │         ◄── EmbeddingClient (embed summary) │
│       │         ◄── vectorstore.upsert_summary      │
│       │                                             │
│  retrieve_context ◄── EmbeddingClient (embed query) │
│       │           ◄── vectorstore.retrieve_top_k    │
│       │                                             │
│  impact_analysis ◄── LLMClient (classify)           │
│       │                                             │
│  generate_docs ◄── Layer1Client (fetch doc file)    │
│       │        ◄── LLMClient (write doc content)    │
│       │                                             │
│  confidence_check                                   │
│       │                                             │
│  format_response                                    │
└───────────────────────┬─────────────────────────────┘
                        │
                        │  ProcessChangeResponse JSON
                        ▼
              Layer 1 opens GitHub PR
```

---

## 3. Data shapes that flow through the system

### 3.1 ProcessChangeRequest — what comes IN

```python
class ProcessChangeRequest(BaseModel):
    repo: str            # "my-api"
    owner: str           # "acme"
    branch: str          # "main"
    installationId: int  # GitHub app installation id (passed through, not used internally)
    commitMessage: str   # "feat: add GET /settings"
    commitId: str        # "abc1234567890"
    changedFiles: List[str]  # ["src/routes/settings.js", ...]
    optional: OptionalPayload | None

class OptionalPayload(BaseModel):
    diffs: Dict[str, str] | None   # { "src/routes/settings.js": "@@ -0,0 +1,12 @@\n+..." }
    repo_size_commits: int | None
```

`diffs` is the raw unified diff text per file. It is optional — if not provided, the pipeline works from file content only.

### 3.2 GraphState — the shared mutable object that every node reads and writes

```python
class GraphState(BaseModel):
    request: ProcessChangeRequest   # original request, never mutated

    # set by validate_input
    repo_id: str                    # "acme/my-api"

    # set by update_memory
    changed_summaries: List[Dict]   # [{"file_path": "src/...", "summary": "..."}]

    # set by retrieve_context
    retrieved_context: List[Dict]   # [{"file_path":..., "summary":..., "score":..., "last_updated_commit":...}]

    # set by impact_analysis
    impact_result: Dict             # {"labels":[], "relevance_score":int, "reasoning":str, "target_docs":[]}

    # set by generate_docs
    generated_files: List[FileUpdate]

    # set by format_response
    pr_title: str | None
    pr_body: str

    # set by confidence_check and format_response
    overall_confidence: str | None  # "High" | "Medium" | "Low"

    # fast-exit flag — any node can set this True to skip remaining generation
    skip_generation: bool
    error: str | None
```

Every node receives the full GraphState, modifies only the fields it owns, and returns it. LangGraph passes it sequentially through nodes.

### 3.3 ProcessChangeResponse — what goes OUT

```python
class ProcessChangeResponse(BaseModel):
    files_to_update: List[FileUpdate]   # empty list = no updates
    pr_title: str | None                # None = no update
    pr_body: str
    confidence: str | None

class FileUpdate(BaseModel):
    path: str           # "docs/api.md"
    content: str        # the new markdown content to write inside the AUTODOCS marker
    confidence: str     # "High" | "Medium" | "Low"
    sources: List[SourceRef]

class SourceRef(BaseModel):
    path: str     # "src/routes/settings.js"
    lines: str    # "1-12"
    score: float  # 0.95 — cosine similarity from vector retrieval
```

---

## 4. Entry point: API layer

### `app/main.py`

One-liner: creates the FastAPI app and attaches the router.

```python
app = FastAPI(title="AutoDocs Layer 2", version="1.0.0")
app.include_router(router)
```

### `app/api.py`

**`_check_secret(x_autodocs_secret)`**
Compares the incoming header value to `settings.autodocs_shared_secret`. Raises HTTP 401 if they don't match. Called before any processing.

**`GET /health`**
Returns `{"status": "ok"}`. Used by docker-compose healthcheck and load balancers.

**`POST /process-change`**
1. Calls `_check_secret()` — aborts with 401 if secret is wrong.
2. Records start time `t0`.
3. Wraps the request in a `GraphState(request=payload)`.
4. Calls `await graph.ainvoke(initial_state)` — this runs the entire LangGraph pipeline and returns the final state.
5. Calculates total duration and logs `commit_process_time_ms` metric to stdout.
6. Unpacks the final state into a `ProcessChangeResponse` and returns it.
7. Any unhandled exception returns HTTP 500 with `{"error": "internal"}`.

---

## 5. The LangGraph pipeline

### `app/langgraph_graph.py`

**`build_graph()`** constructs a `StateGraph` typed to `GraphState`. It registers each agent function as a named node and connects them with directed edges:

```
validate_input
    → update_memory
        → retrieve_context
            → impact_analysis
                → generate_docs
                    → confidence_check
                        → format_response
                            → END
```

There are no conditional branches at the graph level. Instead, nodes check `state.skip_generation` internally and return early without doing work. This keeps the graph topology simple while still short-circuiting expensive operations.

`graph = build_graph()` is called at module import time so the compiled graph is a module-level singleton reused across requests.

---

## 6. Node 1 — validate_input

**File:** `app/agents/classify_change.py`
**Function:** `async def validate_input(state: GraphState) -> GraphState`

### What it does

1. Checks if `state.request.changedFiles` is empty. If so, sets `state.error` and `state.skip_generation = True` and returns immediately. All downstream nodes will be no-ops.
2. Builds `repo_id` as `"owner/repo"` string using `build_repo_id()` and stores it in `state.repo_id`. This string is used as the partition key in the vector store throughout the pipeline.
3. Logs the validation event with `changed_files_count`.

### State fields written

| Field | Value set |
|---|---|
| `repo_id` | `"owner/repo"` |
| `skip_generation` | `True` only if changedFiles is empty |
| `error` | Error message string if invalid |

### Why it exists

Prevents wasted LLM and DB calls for malformed or empty requests. Also centralises the `repo_id` construction so no downstream node has to re-derive it.

---

## 7. Node 2 — update_memory

**File:** `app/agents/update_memory.py`
**Function:** `async def update_memory(state, layer1, embed_client, llm_client) -> GraphState`

This is the **knowledge base maintenance** node. Its job is to keep the vector store up to date with the latest summaries of every changed file.

### Step-by-step for each file in `changedFiles`

```
For each file path:
    1. layer1.fetch_file(path, repo, owner, branch)
           → GET Layer1 /file-content?path=...
           → returns raw file content string

    2. If content is empty (file deleted):
           vectorstore.delete_summary(repo_id, path)
           → DELETE FROM summaries WHERE repo_id=$1 AND file_path=$2
           → skip to next file

    3. Build user prompt:
           "File: {path}\n\nContent:\n{content[:4000]}"
           (truncated to 4000 chars to stay within LLM context)

    4. llm_client.complete(SUMMARIZE_PROMPT, user_prompt, temperature=0.1)
           → POST Ollama /api/chat
           → returns 150-200 word factual summary string

    5. embed_client.embed(summary)
           → POST Ollama /api/embeddings
           → returns List[float] of length EMBEDDING_DIM (e.g. 768 or 1536)

    6. vectorstore.upsert_summary(repo_id, path, summary, embedding, commitId)
           → INSERT ... ON CONFLICT (repo_id, file_path) DO UPDATE
           → stores summary text + vector in DB

    7. Append {"file_path": path, "summary": summary} to local list
```

### State fields written

| Field | Value set |
|---|---|
| `changed_summaries` | List of `{"file_path": str, "summary": str}` for each successfully processed file |

### Why summaries and not raw code

Raw code is too large to fit in prompts for all context files at once. A 150-200 word summary captures the public API surface, exported functions, env vars, and dependencies — exactly what documentation cares about — in a token-efficient form. The summary is also what gets embedded, so semantic search finds conceptually related files rather than syntactically similar ones.

### Dependency injection

`layer1`, `embed_client`, `llm_client` default to `None` and are instantiated inside the function if not provided. This pattern makes unit testing easy — tests pass mock objects instead.

---

## 8. Node 3 — retrieve_context

**File:** `app/agents/retrieve_context.py`
**Function:** `async def retrieve_context(state, embed_client) -> GraphState`

This is the **RAG retrieval** node. It finds files in the vector store that are semantically related to the current change, even if those files weren't changed in this commit.

### Step-by-step

```
1. Build query text (max 8000 chars):
       diffs_text = join all diff strings from request.optional.diffs
       summaries_text = join all summaries from state.changed_summaries
       query_text = (diffs_text + "\n" + summaries_text)[:8000]

   Why combine diffs + summaries?
   Diffs show what changed (syntax-level).
   Summaries show what the files do (semantic-level).
   Together they produce a richer query embedding.

2. embed_client.embed(query_text)
       → POST Ollama /api/embeddings
       → returns query embedding vector

3. vectorstore.retrieve_top_k(query_embedding, repo_id, RETRIEVAL_K)
       → SELECT ... ORDER BY embedding <=> query_vector LIMIT K
       → cosine distance search (pgvector <=> operator)
       → returns [{file_path, summary, score, last_updated_commit}]
       → score = 1 - cosine_distance (so 1.0 = identical, 0.0 = unrelated)

4. Store results in state.retrieved_context
```

### Fallback on failure

If embedding fails (Ollama down, model not loaded, etc.), the exception is caught, `state.retrieved_context` is set to `[]`, and a `reliability_note` is logged. The pipeline continues without retrieved context — `generate_docs` will still work using `changed_summaries` alone.

### State fields written

| Field | Value set |
|---|---|
| `retrieved_context` | List of vector store rows with `file_path`, `summary`, `score`, `last_updated_commit`. Empty list on failure. |

### Why this matters

Imagine a commit that changes `src/auth/middleware.js`. The diff doesn't mention any routes. But the vector store knows that `src/routes/profile.js` imports and calls that middleware — its summary says so. Retrieve context finds that file and includes its summary in the generation prompt, allowing the LLM to write accurate documentation that mentions the impact on the `/profile` endpoint.

---

## 9. Node 4 — impact_analysis

**File:** `app/agents/impact_analysis.py`
**Function:** `async def impact_analysis(state, llm_client) -> GraphState`

This node decides **whether docs need updating at all**, and if so, **which doc files** to update. It uses two layers: deterministic regex rules first, then LLM classification to catch edge cases.

### Layer 1: rule-based labels (`_rule_based_labels`)

Runs pure regex against file paths and diff text — no LLM, instant, free:

| Rule | Pattern | Label assigned |
|---|---|---|
| File path is a dependency manifest | `package.json`, `requirements.txt`, `pyproject.toml`, `setup.cfg` | `DEPENDENCY_UPDATE` |
| File path is an env file | `.env`, `env.example` | `NEW_ENV_VARIABLE` |
| Diff adds a route registration | `router.get(`, `app.post(`, etc. | `NEW_API_ROUTE` |
| Diff adds an exported function | `+export async function ...` | `FUNCTION_SIGNATURE_CHANGE` |
| Diff adds an ALL_CAPS variable | `+MY_VAR =` | `NEW_ENV_VARIABLE` |

### Layer 2: LLM classification

Sends to Ollama with `temperature=0.0` (deterministic):
- Changed file paths
- Commit message  
- Diff snippet (first 3 files, max 2000 chars)
- Rule-based labels already found

LLM returns JSON: `{"labels": [...], "relevance_score": 0-100, "reasoning": "..."}`.

Final labels = union of rule labels + LLM labels (deduped).

### CHANGE_DOC_MAP — the routing table

```python
CHANGE_DOC_MAP = {
    "NEW_API_ROUTE":              [("docs/api.md", "ROUTES")],
    "NEW_ENV_VARIABLE":           [("docs/env.md", "ENV")],
    "DEPENDENCY_UPDATE":          [("docs/setup.md", "INSTALL")],
    "FUNCTION_SIGNATURE_CHANGE":  [("docs/api.md", "ROUTES")],
    "NEW_MODULE":                 [("docs/architecture.md", "MODULES")],
    "INTERNAL_REFACTOR":          [],   # no doc update
    "COMMENT_ONLY":               [],   # no doc update
}
```

Each label maps to a `(doc_file_path, marker_section_name)` tuple. Multiple labels can map to the same doc file — these are deduped by file path before passing downstream.

### The skip decision

```python
if relevance_score < settings.relevance_threshold or not target_docs:
    state.skip_generation = True
```

Default threshold is 70. If the LLM says relevance is 65 (minor internal refactor), or if all labels map to empty lists (INTERNAL_REFACTOR, COMMENT_ONLY), the pipeline fast-exits and returns "No doc updates suggested."

### State fields written

| Field | Value set |
|---|---|
| `impact_result` | `{"labels": [...], "relevance_score": int, "reasoning": str, "target_docs": [(path, marker), ...]}` |
| `skip_generation` | `True` if score below threshold or no target docs |

---

## 10. Node 5 — generate_docs

**File:** `app/agents/generate_docs.py`
**Function:** `async def generate_docs(state, layer1, llm_client) -> GraphState`

This is the core generation node. For each target doc file identified by `impact_analysis`, it fetches the existing doc, extracts the relevant section, and asks the LLM to write updated content for that section.

### Step-by-step for each `(doc_path, marker_section)` in `target_docs`

```
1. layer1.fetch_file(doc_path, repo, owner, branch)
       → fetches the current content of e.g. "docs/api.md"
       → if fetch fails, doc_content = "" (treat as new file)

2. extract_marker_content(doc_content, marker_section)
       → finds text between <!-- AUTODOCS:ROUTES_START --> and <!-- AUTODOCS:ROUTES_END -->
       → returns that text as "existing_marker" string
       → if markers not present, returns ""

3. Build user message:
       - Doc file path + marker section name
       - Existing marker content (so LLM can preserve + extend, not overwrite)
       - Changed file summaries (from state.changed_summaries)
       - Retrieved context summaries (from state.retrieved_context, with scores)
       - Diff text (up to 3000 chars)
       - Instruction: return ONLY JSON {content, confidence, sources}

4. llm_client.complete(STYLE_GUIDE_PROMPT, user_msg, temperature=0.1)
       → POST Ollama /api/chat with style guide as system prompt
       → returns raw string

5. parse_llm_json(raw)
       → strips markdown fences if present
       → JSON.loads
       → fallback: find first { ... } if parse fails

6. Build FileUpdate(path=doc_path, content=..., confidence=..., sources=[SourceRef(...)])

7. Append to files_to_update list
```

### What the LLM is given in context

The generation prompt gives the LLM four types of context simultaneously:

| Context | Source | Purpose |
|---|---|---|
| Existing section content | Fetched from Layer1 | Preserve unrelated parts, extend related parts |
| Changed file summaries | `state.changed_summaries` | Direct knowledge of what changed |
| Retrieved context summaries | `state.retrieved_context` | Knowledge of related files that didn't change |
| Diff text | `request.optional.diffs` | Exact line-level changes |

### State fields written

| Field | Value set |
|---|---|
| `generated_files` | `List[FileUpdate]` — one entry per target doc that was successfully generated |

---

## 11. Node 6 — confidence_check

**File:** `app/agents/confidence.py`
**Function:** `async def confidence_check(state) -> GraphState`

Post-processes the generated files with heuristic quality checks. No LLM call.

### Rules applied

```python
for each FileUpdate in generated_files:
    if file.confidence == "Low":
        review_required = True

    if "UNVERIFIED" in file.content:
        # LLM itself flagged something it couldn't verify
        file.confidence = "Low"
        review_required = True
```

### Overall confidence roll-up

```
if any file is "Low"    → overall_confidence = "Low"
elif any file is "Medium" → overall_confidence = "Medium"
else                    → overall_confidence = "High"
```

### PR body annotation

If `review_required` is True, appends to `state.pr_body`:
```
⚠️ review_required: Some sections have Low confidence or UNVERIFIED statements.
```

This tells Layer 1 (and the human reviewer) not to auto-merge this PR.

### State fields written

| Field | Value set |
|---|---|
| `overall_confidence` | `"High"` / `"Medium"` / `"Low"` |
| `pr_body` | Appended with review warning if needed |
| Individual `FileUpdate.confidence` | Downgraded to `"Low"` if UNVERIFIED found |

---

## 12. Node 7 — format_response

**File:** `app/agents/format_response.py`
**Function:** `async def format_response(state) -> GraphState`

Final node. Assembles the human-readable PR metadata.

### No-update path

If `skip_generation` is True or `generated_files` is empty:
```python
state.pr_title = None
state.pr_body = "No doc updates suggested."
state.overall_confidence = None
```

### Update path

```python
state.pr_title = f"📝 AutoDocs: {label_str} ({commitId[:7]})"
# e.g. "📝 AutoDocs: NEW_API_ROUTE, DEPENDENCY_UPDATE (abc1234)"

state.pr_body = f"""
Automated documentation updates for commit `{commitId}`.

**Updated docs:**
- `docs/api.md` (High)
- `docs/setup.md` (Medium)

**Overall confidence:** High
"""
```

The `pr_body` may already have the review warning appended by `confidence_check` — `format_response` does not overwrite it.

### State fields written

| Field | Value set |
|---|---|
| `pr_title` | String or None |
| `pr_body` | Full PR body markdown |

---

## 13. Tools in depth

### 13.1 Layer1Client (`app/tools/layer1_client.py`)

Async HTTP client that talks to the Layer 1 service. All requests carry `X-AUTODOCS-SECRET` header.

**`fetch_file(path, repo, owner, branch) → str`**
- `GET {LAYER1_BASE_URL}/file-content?path=...&repo=...&owner=...&branch=...`
- Returns raw file content string.
- Used by: `update_memory` (for source files), `generate_docs` (for existing doc files).
- Timeout: 15 seconds.

**`fetch_diff(path, repo, owner, branch, commit_id) → str`**
- `GET {LAYER1_BASE_URL}/file-diff?...`
- Returns unified diff string for a single file.
- Available but not called by default — diffs are expected in the request payload from Layer1.
- Timeout: 15 seconds.

**`patch_files(owner, repo, branch, files) → dict`**
- `POST {LAYER1_BASE_URL}/apply-patch`
- Body: `{"owner":..., "repo":..., "branch":..., "files": [{path, content}]}`
- Tells Layer 1 to write file patches and open a PR.
- Used by `scaffold.py` callers (not called inside the main pipeline — Layer 1 uses the response JSON to do this itself).
- Timeout: 30 seconds.

### 13.2 LLMClient (`app/tools/llm_client.py`)

Wraps Ollama's `/api/chat` endpoint.

**`complete(system, user, temperature=0.1) → str`**
- Sends a two-message conversation: system role (the prompt template) + user role (the dynamic content).
- `stream: false` — waits for the full response before returning.
- Temperature is always ≤ 0.2 (callers pass 0.0 or 0.1).
- Retry logic: on any exception, sleeps 2 seconds and tries once more. If second attempt fails, raises `RuntimeError`.
- Timeout: 120 seconds (LLMs can be slow locally).

Called with three different system prompts:
| Caller | Temperature | System prompt used |
|---|---|---|
| `update_memory` (summarise) | 0.1 | `summarize_file.prompt.txt` |
| `impact_analysis` (classify) | 0.0 | `classify_change.prompt.txt` |
| `generate_docs` (write docs) | 0.1 | `generate_doc_update.prompt.txt` |

### 13.3 EmbeddingClient (`app/tools/embedding_client.py`)

Wraps Ollama's `/api/embeddings` endpoint.

**`embed(text) → List[float]`**
- `POST {OLLAMA_API_URL}/api/embeddings` with `{"model": EMBED_MODEL, "prompt": text}`.
- Returns the embedding vector as a Python list of floats.
- Length must match `EMBEDDING_DIM` (set in config, must match what the model actually produces).
- Retry: sleeps 1 second on first failure, raises on second.
- Timeout: 30 seconds.

Called by:
- `update_memory`: embeds each file summary before storing.
- `retrieve_context`: embeds the combined query text before searching.

### 13.4 vectorstore (`app/tools/vectorstore.py`)

Thin async layer over `asyncpg` (raw Postgres driver).

**`get_pool() → asyncpg.Pool`**
Lazy singleton. Creates a connection pool on first call using `PG_DSN`. Reused for all subsequent calls within a process lifetime.

**`upsert_summary(repo_id, path, summary, embedding, commit_id)`**
```sql
INSERT INTO summaries (repo_id, file_path, summary, embedding, last_updated_commit, updated_at)
VALUES ($1, $2, $3, $4::vector, $5, now())
ON CONFLICT (repo_id, file_path) DO UPDATE SET ...
```
The embedding list is serialised to a pgvector-compatible string: `"[0.1, 0.2, ...]"` and cast with `::vector`.

**`delete_summary(repo_id, path)`**
```sql
DELETE FROM summaries WHERE repo_id = $1 AND file_path = $2
```
Called when a file is deleted from the repo (Layer1 returns empty content for it).

**`retrieve_top_k(query_embedding, repo_id, k) → List[Dict]`**
```sql
SELECT file_path, summary, last_updated_commit,
       1 - (embedding <=> $1::vector) AS score
FROM summaries
WHERE repo_id = $2
ORDER BY embedding <=> $1::vector
LIMIT $3
```
`<=>` is pgvector's cosine distance operator. `1 - cosine_distance` gives cosine similarity (1 = identical, 0 = orthogonal). Results are already scoped to the current repo via `WHERE repo_id = $2`.

---

## 14. Utilities in depth

### `app/utils.py`

**`log(node, event, repo_id, commit_id, duration_ms, details)`**
Emits a JSON-structured log line to stdout via Python's `logging` module. Every log line is a single JSON object. Example:
```json
{"timestamp": "2024-01-15T10:23:45Z", "repo_id": "acme/my-api", "commit_id": "abc123", "node": "update_memory", "event": "upserted", "duration_ms": 342.5, "details": {"path": "src/routes/settings.js"}}
```

**`log_metric(metric, value, repo, commit)`**
Prints a JSON metric line directly to stdout (bypasses logging module). Used for timing the full request:
```json
{"metric": "commit_process_time_ms", "value": 4521.3, "repo": "my-api", "commit": "abc123"}
```

**`extract_marker_content(text, section) → str`**
Finds `<!-- AUTODOCS:{section}_START -->` and `<!-- AUTODOCS:{section}_END -->` in `text` and returns everything between them. Returns `""` if either tag is missing. Used in `generate_docs` to get the existing content of a doc section.

**`replace_marker_content(text, section, new_content) → str`**
Replaces the content between the marker tags. If the markers don't exist in the text, appends a new marker block at the end. Always inserts the `<!-- Managed by AutoDocs v1 -->` notice line inside the marker. This function is the one that would be called if Layer 2 were applying patches itself — in practice, it returns `content` to Layer 1 which handles file writing.

**`parse_llm_json(raw) → dict`**
Defensive JSON parser for LLM output:
1. Strips leading/trailing whitespace.
2. If response starts with `` ` `` (markdown fence), strips the fence lines.
3. Tries `json.loads()`.
4. On failure, finds the first `{` and last `}` and tries to parse that substring.
5. If still failing, re-raises the `JSONDecodeError`.

**`build_repo_id(owner, repo) → str`**
Returns `f"{owner}/{repo}"`. Simple but centralised so the format is consistent everywhere.

### `app/config.py`

Pydantic `BaseSettings` subclass. Reads from environment variables and optionally a `.env` file. The `@lru_cache()` decorator on `get_settings()` means the settings object is created once and reused — env vars are read once at startup, not on every request.

---

## 15. Prompts in depth

### `summarize_file.prompt.txt` — system prompt for file summarisation

```
You are a code summarizer. Produce a factual 150-200 word summary of the given source file.
Include: exported functions/routes/classes, public API surface, environment variables used, primary dependencies imported.
Do not include implementation details, comments, or opinions.
Return only the summary paragraph, no preamble or labels.
```

**What the user message looks like:**
```
File: src/routes/settings.js

Content:
const router = require('express').Router();
router.get('/settings', async (req, res) => {
  const settings = await getSettings();
  res.json(settings);
});
module.exports = router;
```

**Why this matters for retrieval:** The summary captures semantic meaning — "exports a GET /settings route, returns application settings" — which embeds into a vector that clusters near other API-related files. Raw code would embed based on syntax, not meaning.

### `classify_change.prompt.txt` — system prompt for change classification

```
You are a code change classifier. Given changed files, commit message, and a diff snippet, classify the change.
Valid labels: NEW_API_ROUTE, NEW_ENV_VARIABLE, DEPENDENCY_UPDATE, FUNCTION_SIGNATURE_CHANGE, NEW_MODULE, INTERNAL_REFACTOR, COMMENT_ONLY.
Return ONLY valid JSON with no preamble:
{"labels": ["LABEL1", ...], "relevance_score": 0-100, "reasoning": "one sentence"}
relevance_score: how relevant this change is to documentation (100 = must update docs, 0 = no docs impact).
```

Temperature is set to `0.0` here — maximum determinism. The output is pure routing logic; we don't want creative variation.

### `generate_doc_update.prompt.txt` — system prompt for doc generation

This is the full style guide. Key constraints it enforces:
- **Format:** headings, bullet lists for params, fenced code examples.
- **Endpoint docs:** Method, Path, Description, Parameters table, Response example, Error codes.
- **Env var docs:** Name, Required/Optional, Default, Purpose.
- **SOURCE: field:** Every paragraph ends with `SOURCE: path:line-line` so humans can verify.
- **CONFIDENCE: tag:** Every paragraph ends with `CONFIDENCE: High/Medium/Low`.
- **UNVERIFIED:** prefix and `CONFIDENCE: Low` if the model can't find evidence in provided context.
- **Output format:** Strictly JSON `{"content": "...", "confidence": "...", "sources": [...]}` — no preamble, no fences.

The `confidence_check` node reads the generated `content` string looking for the literal word `"UNVERIFIED"` — so if the LLM follows the style guide and prefixes unverifiable statements, the system automatically downgrades confidence.

---

## 16. Database schema and vector store

### `app/schema/create_tables.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS summaries (
  id SERIAL PRIMARY KEY,
  repo_id TEXT NOT NULL,          -- "acme/my-api" — partition key
  file_path TEXT NOT NULL,        -- "src/routes/settings.js"
  summary TEXT NOT NULL,          -- 150-200 word LLM summary
  embedding vector(1536),         -- EMBEDDING_DIM floats
  last_updated_commit TEXT,       -- commit SHA that last changed this file
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (repo_id, file_path)     -- one row per file per repo
);

CREATE INDEX idx_summaries_repo_path ON summaries (repo_id, file_path);
CREATE INDEX idx_summaries_embedding ON summaries
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### Index types explained

**`idx_summaries_repo_path`**: B-tree index on `(repo_id, file_path)`. Makes point lookups (upsert conflict detection, delete by path) fast.

**`idx_summaries_embedding`**: IVFFlat (Inverted File Flat) index for approximate nearest neighbour search. `lists = 100` means the index partitions vectors into 100 clusters. For cosine distance (`vector_cosine_ops`). Speeds up `retrieve_top_k` dramatically once the table has thousands of rows.

### What is NOT stored

Raw file source code is never stored. Only summaries and their vectors. This keeps the DB small, avoids accidental secret storage, and is sufficient for all downstream uses.

---

## 17. Observability layer

### `app/observability.py`

**`_get_client()`**
Lazy initialises the LangSmith `Client` singleton. Only creates it if `ENABLE_LANGSMITH=true` AND `LANGSMITH_API_KEY` is set. If LangSmith is unavailable (import error, network issue), returns `None` silently — the service never crashes due to observability failures.

**`trace_node(run_name, inputs, parent_run_id)` — context manager**

```python
with trace_node("update_memory", {"files": [...], "commit": "abc"}):
    # ... node work ...
```

If LangSmith client is available:
1. Creates a LangSmith run with masked inputs.
2. Yields the run ID (can be used to create child runs).
3. On exit, updates the run with end time.

If LangSmith is not configured: yields `None`, no-op. The `with` block still executes normally.

**`_mask_secrets(data)`**
Scans dict keys for words like `secret`, `token`, `password`, `api_key`, `authorization` and replaces their values with `"***"`. Prevents secrets from appearing in LangSmith traces.

### Structured JSON logs (utils.py)

Every node calls `log(node, event, ...)` which emits to Python's `logging` module at INFO level as a JSON string. Log level is controlled by `LOG_LEVEL` env var.

Metric lines (timing) are printed directly to stdout as JSON, separate from the log stream, so they can be parsed by log aggregators independently.

---

## 18. Scaffold utility

### `app/scaffold.py`

**`scaffold_docs(repo_id, owner, branch) → List[Dict]`**

Returns a list of file patches to create the initial documentation structure for a new repo. Does not call any external service — just returns data.

Files scaffolded:
```
README.md        → OVERVIEW marker
docs/api.md      → ROUTES marker
docs/architecture.md → MODULES marker
docs/setup.md    → INSTALL marker
docs/env.md      → ENV marker
```

Each patch has shape `{"path": "docs/api.md", "content": "# Api\n\n<!-- AUTODOCS:ROUTES_START -->\n..."}`.

The caller (typically Layer 1 on first installation) passes these patches to `layer1_client.patch_files()` to write them to the repo. Scaffold is idempotent — if the files already exist, Layer 1 can choose not to overwrite.

---

## 19. The skip_generation fast-exit flag

`state.skip_generation` is the system's way of short-circuiting without needing conditional graph edges. Any node can set it `True`. Every node (except `validate_input` and `format_response`) checks it at the top:

```python
if state.skip_generation:
    return state
```

This means:
- `validate_input` sets it → all downstream nodes are no-ops → `format_response` returns "No doc updates suggested."
- `impact_analysis` sets it (low relevance score) → `generate_docs`, `confidence_check` are skipped → `format_response` returns "No doc updates suggested."
- No expensive LLM or DB calls happen after the flag is set.

`format_response` does NOT check this flag first — it runs always and handles the flag by choosing which response to build.

---

## 20. Full data flow trace for a real commit

**Scenario:** Developer pushes a commit adding `GET /settings` to `src/routes/settings.js`.

### Request arrives

```json
POST /process-change
X-AUTODOCS-SECRET: changeme

{
  "repo": "my-api", "owner": "acme", "branch": "main",
  "commitId": "abc1234567890", "commitMessage": "feat: add GET /settings",
  "changedFiles": ["src/routes/settings.js"],
  "optional": {
    "diffs": {
      "src/routes/settings.js": "@@ -0,0 +1,8 @@\n+router.get('/settings', ...)"
    }
  }
}
```

### Node 1 — validate_input

- `changedFiles` not empty ✓
- `state.repo_id = "acme/my-api"`
- Logs: `{"node":"validate_input","event":"validated","details":{"changed_files_count":1}}`

### Node 2 — update_memory

- `layer1.fetch_file("src/routes/settings.js", "my-api", "acme", "main")` → returns JS source.
- LLM summarises: `"This module exports a GET /settings route using Express Router. It calls getSettings() and returns the result as JSON. Imports express Router. No environment variables used."`
- Embed that summary → `[0.12, -0.34, 0.07, ...]` (1536 floats)
- Upserts to DB: row for `("acme/my-api", "src/routes/settings.js")` with summary + vector.
- `state.changed_summaries = [{"file_path": "src/routes/settings.js", "summary": "This module exports..."}]`

### Node 3 — retrieve_context

- Query text = diff text + summary text (both about GET /settings).
- Embed query → query vector.
- `retrieve_top_k(query_vector, "acme/my-api", 5)` → DB finds 5 closest rows.
  - Might return `src/routes/profile.js` (score 0.73) and `src/middleware/auth.js` (score 0.61) — files that deal with similar route patterns.
- `state.retrieved_context = [{file_path: "src/routes/profile.js", summary: "...", score: 0.73}, ...]`

### Node 4 — impact_analysis

- Rule-based: diff contains `router.get(` → label `NEW_API_ROUTE`.
- LLM confirms: `{"labels": ["NEW_API_ROUTE"], "relevance_score": 92, "reasoning": "adds a new Express GET route"}`.
- `target_docs = [("docs/api.md", "ROUTES")]`
- `relevance_score=92 >= threshold=70` → `skip_generation` stays False.

### Node 5 — generate_docs

For `("docs/api.md", "ROUTES")`:
- Fetch `docs/api.md` from Layer1 → returns existing content (has AUTODOCS:ROUTES markers).
- `extract_marker_content(doc_content, "ROUTES")` → existing routes section.
- Build user message with: existing section, changed summaries, retrieved context summaries, diff.
- LLM (style guide prompt, temp=0.1) generates:
  ```json
  {
    "content": "## GET /settings\n\nReturns application settings.\n\n**Response**\n```json\n{...}\n```\n\nSOURCE: src/routes/settings.js:1-8\nCONFIDENCE: High",
    "confidence": "High",
    "sources": [{"path": "src/routes/settings.js", "lines": "1-8", "score": 0.95}]
  }
  ```
- `state.generated_files = [FileUpdate(path="docs/api.md", content="## GET /settings...", confidence="High", sources=[...])]`

### Node 6 — confidence_check

- `"High"` confidence, no `"UNVERIFIED"` in content.
- `state.overall_confidence = "High"`
- No review_required flag.

### Node 7 — format_response

- `state.pr_title = "📝 AutoDocs: NEW_API_ROUTE (abc1234)"`
- `state.pr_body = "Automated documentation updates for commit \`abc1234567890\`.\n\n**Updated docs:**\n- \`docs/api.md\` (High)\n\n**Overall confidence:** High\n"`

### Response returned to Layer1

```json
{
  "files_to_update": [
    {
      "path": "docs/api.md",
      "content": "## GET /settings\n\nReturns application settings...\n\nSOURCE: src/routes/settings.js:1-8\nCONFIDENCE: High",
      "confidence": "High",
      "sources": [{"path": "src/routes/settings.js", "lines": "1-8", "score": 0.95}]
    }
  ],
  "pr_title": "📝 AutoDocs: NEW_API_ROUTE (abc1234)",
  "pr_body": "Automated documentation updates for commit `abc1234567890`...",
  "confidence": "High"
}
```

Layer 1 takes this, writes `content` into the AUTODOCS:ROUTES marker in `docs/api.md`, and opens a PR.

---

## 21. Error handling and resilience map

| Where | What can fail | What happens |
|---|---|---|
| `update_memory` — `fetch_file` | Layer1 unreachable | Exception caught per-file, logged, that file skipped. Other files still processed. |
| `update_memory` — LLM summarise | Ollama down / model missing | 1 retry with 2s backoff. If still fails, raises; caught by outer try/except, file skipped. |
| `update_memory` — `embed` | Ollama down | 1 retry with 1s backoff. If still fails, raises; caught, file skipped. |
| `update_memory` — DB upsert | Postgres down | Exception caught, file skipped, logged. |
| `retrieve_context` — `embed` | Ollama down | Exception caught. `state.retrieved_context = []`. Pipeline continues with summaries only. `reliability_note` logged. |
| `retrieve_context` — DB query | Postgres down | Exception caught. `state.retrieved_context = []`. Pipeline continues. |
| `impact_analysis` — LLM classify | Ollama down | Falls back to rule-based labels only. `relevance_score` set to 60 (if rules found labels) or 20 (if not). |
| `generate_docs` — `fetch_file` (doc) | Layer1 unreachable | `doc_content = ""`. Generation proceeds with empty existing section. |
| `generate_docs` — LLM generate | Ollama down / bad JSON | File skipped, logged. Other target docs still processed. |
| `generate_docs` — `parse_llm_json` | LLM returns non-JSON | Fallback parser tries to extract `{...}`. If still fails, file skipped. |
| `api.py` — any unhandled exception | Any unexpected error | HTTP 500 `{"error":"internal"}`. Layer1 is notified, not hung. |
| LangSmith | Unavailable / key wrong | Silently ignored. Service continues without tracing. |

---

## 22. Config and how every setting is used

| Setting | Used by | Effect |
|---|---|---|
| `AUTODOCS_SHARED_SECRET` | `api.py` `_check_secret()`, `Layer1Client` headers | Authentication on all incoming requests and all Layer1 outbound calls |
| `OLLAMA_API_URL` | `LLMClient`, `EmbeddingClient` | Base URL for all Ollama API calls |
| `OLLAMA_LLM_MODEL_NAME` | `LLMClient` | Which Ollama model to use for summarisation, classification, doc generation |
| `OLLAMA_EMBED_MODEL_NAME` | `EmbeddingClient` | Which Ollama model to use for embedding |
| `PG_DSN` | `vectorstore.get_pool()` | Postgres connection string for asyncpg pool |
| `EMBEDDING_DIM` | `create_tables.sql` (manual) | Must match what `OLLAMA_EMBED_MODEL_NAME` actually produces. Not enforced at runtime — mismatch causes DB errors. |
| `RETRIEVAL_K` | `retrieve_context` node | How many vector store results to include in generation context |
| `RELEVANCE_THRESHOLD` | `impact_analysis` node | Score below this → `skip_generation=True` → no doc update |
| `ENABLE_LANGSMITH` | `observability._get_client()` | Master switch for LangSmith tracing |
| `LANGSMITH_API_KEY` | `observability._get_client()` | LangSmith auth |
| `LAYER1_BASE_URL` | `Layer1Client` | Where to fetch files and post patches |
| `LOG_LEVEL` | `utils.py` logging setup | Controls log verbosity (`debug`, `info`, `warning`, `error`) |
