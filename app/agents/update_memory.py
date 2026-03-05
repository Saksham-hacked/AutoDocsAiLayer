import time
from app.models import GraphState
from app.tools.layer1_client import Layer1Client
from app.tools.embedding_client import EmbeddingClient
from app.tools.llm_client import LLMClient
from app.tools import vectorstore
from app.utils import log, log_metric
from app.observability import trace_node
from app.config import get_settings
from pathlib import Path

settings = get_settings()
_SUMMARIZE_PROMPT = (Path(__file__).parent.parent / "prompts" / "summarize_file.prompt.txt").read_text()


async def update_memory(state: GraphState, layer1: Layer1Client = None, embed_client: EmbeddingClient = None, llm_client: LLMClient = None) -> GraphState:
    if state.skip_generation:
        return state

    layer1 = layer1 or Layer1Client()
    embed_client = embed_client or EmbeddingClient()
    llm_client = llm_client or LLMClient()
    req = state.request
    summaries = []

    with trace_node("update_memory", {"files": req.changedFiles, "commit": req.commitId}):
        for path in req.changedFiles:
            t0 = time.time()
            try:
                content = await layer1.fetch_file(path, req.repo, req.owner, req.branch)
                if not content:
                    await vectorstore.delete_summary(state.repo_id, path)
                    log("update_memory", "deleted_summary", repo_id=state.repo_id, commit_id=req.commitId, details={"path": path})
                    continue

                user_prompt = f"File: {path}\n\nContent:\n{content[:4000]}"
                summary = await llm_client.complete(_SUMMARIZE_PROMPT, user_prompt, temperature=0.1)
                embedding = await embed_client.embed(summary)
                await vectorstore.upsert_summary(state.repo_id, path, summary, embedding, req.commitId)
                summaries.append({"file_path": path, "summary": summary})
                dur = (time.time() - t0) * 1000
                log("update_memory", "upserted", repo_id=state.repo_id, commit_id=req.commitId,
                    duration_ms=dur, details={"path": path})
            except Exception as e:
                log("update_memory", "error", repo_id=state.repo_id, commit_id=req.commitId,
                    details={"path": path, "error": str(e)})

    state.changed_summaries = summaries
    return state
