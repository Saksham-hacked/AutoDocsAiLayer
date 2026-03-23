import asyncio
import time
from app.models import GraphState
from app.tools.layer1_client import Layer1Client
from app.tools.embedding_client import EmbeddingClient
from app.tools.llm_client import LLMClient
from app.tools import vectorstore
from app.utils import log
from app.observability import trace_node
from app.config import get_settings
from pathlib import Path

settings = get_settings()
_SUMMARIZE_PROMPT = (Path(__file__).parent.parent / "prompts" / "summarize_file.prompt.txt").read_text()

# Max files processed simultaneously — prevents Gemini rate limiting
_CONCURRENCY_LIMIT = 5


async def _process_single_file(
    path: str,
    state: GraphState,
    req,
    diff_fallback: dict,
    layer1: Layer1Client,
    llm_client: LLMClient,
    embed_client: EmbeddingClient,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    async with semaphore:
        t0 = time.time()
        content = None

        # 1. Try to fetch full file content from Layer1
        try:
            content = await layer1.fetch_file(path, req.repo, req.owner, req.branch, req.installationId)
            log("update_memory", "fetched_from_layer1", repo_id=state.repo_id,
                commit_id=req.commitId, details={"path": path})
        except Exception as e:
            log("update_memory", "layer1_unavailable", repo_id=state.repo_id,
                commit_id=req.commitId, details={"path": path, "error": str(e)})

        # 2. If Layer1 failed or returned empty, fall back to diff text from payload
        if not content:
            content = diff_fallback.get(path, "")
            if content:
                log("update_memory", "using_diff_fallback", repo_id=state.repo_id,
                    commit_id=req.commitId, details={"path": path})

        # 3. If still empty, file was deleted — remove from vector store
        if not content:
            try:
                await vectorstore.delete_summary(state.repo_id, path)
            except Exception:
                pass
            log("update_memory", "deleted_summary", repo_id=state.repo_id,
                commit_id=req.commitId, details={"path": path})
            return None

        # 4. Summarise with LLM
        try:
            user_prompt = f"File: {path}\n\nContent:\n{content[:40000]}"
            summary = await llm_client.complete(_SUMMARIZE_PROMPT, user_prompt, temperature=0.1)
            log("update_memory", "summarised", repo_id=state.repo_id,
                commit_id=req.commitId, details={"path": path, "summary_len": len(summary)})
        except Exception as e:
            log("update_memory", "llm_error", repo_id=state.repo_id,
                commit_id=req.commitId, details={"path": path, "error": str(e)})
            summary = f"File {path} was modified in commit {req.commitId}. Diff: {content[:300]}"

        # 5. Embed the summary
        try:
            embedding = await embed_client.embed(summary)
            await vectorstore.upsert_summary(state.repo_id, path, summary, embedding, req.commitId)
            log("update_memory", "upserted", repo_id=state.repo_id,
                commit_id=req.commitId, duration_ms=round((time.time() - t0) * 1000, 2),
                details={"path": path})
        except Exception as e:
            log("update_memory", "embed_or_db_error", repo_id=state.repo_id,
                commit_id=req.commitId, details={"path": path, "error": str(e)})

        return {"file_path": path, "summary": summary}


async def update_memory(
    state: GraphState,
    layer1: Layer1Client = None,
    embed_client: EmbeddingClient = None,
    llm_client: LLMClient = None,
) -> GraphState:
    if state.skip_generation:
        return state

    layer1 = layer1 or Layer1Client()
    embed_client = embed_client or EmbeddingClient()
    llm_client = llm_client or LLMClient()
    req = state.request

    # Pre-build a fallback content map from diffs in the request payload
    # so we can work even when Layer1 is not reachable
    diff_fallback = {}
    if req.optional and req.optional.diffs:
        diff_fallback = req.optional.diffs  # {path: diff_text}

    # Never summarise AutoDocs-managed doc files — wastes LLM calls and pollutes context
    DOC_PREFIXES = ("docs/",)
    source_files = [f for f in req.changedFiles if not f.startswith(DOC_PREFIXES)]

    semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)

    with trace_node("update_memory", {"files": source_files, "commit": req.commitId}):
        results = await asyncio.gather(*[
            _process_single_file(path, state, req, diff_fallback, layer1, llm_client, embed_client, semaphore)
            for path in source_files
        ], return_exceptions=True)

        # Filter out None (deleted files) and any exceptions (failed files)
        summaries = [r for r in results if isinstance(r, dict)]

    state.changed_summaries = summaries
    log("update_memory", "complete", repo_id=state.repo_id, commit_id=req.commitId,
        details={"summaries_count": len(summaries)})
    return state
