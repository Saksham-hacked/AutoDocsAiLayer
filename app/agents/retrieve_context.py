from app.models import GraphState
from app.tools.embedding_client import EmbeddingClient
from app.tools import vectorstore
from app.utils import log
from app.observability import trace_node
from app.config import get_settings

settings = get_settings()
MAX_QUERY_CHARS = 8000


async def retrieve_context(state: GraphState, embed_client: EmbeddingClient = None) -> GraphState:
    if state.skip_generation:
        return state

    embed_client = embed_client or EmbeddingClient()
    req = state.request

    diffs_text = ""
    if req.optional and req.optional.diffs:
        diffs_text = "\n".join(req.optional.diffs.values())

    summaries_text = "\n".join(s["summary"] for s in state.changed_summaries)
    query_text = (diffs_text + "\n" + summaries_text)[:MAX_QUERY_CHARS]

    with trace_node("retrieve_context", {"repo_id": state.repo_id}):
        try:
            embedding = await embed_client.embed(query_text)
            results = await vectorstore.retrieve_top_k(embedding, state.repo_id, settings.retrieval_k)
            state.retrieved_context = results
            log("retrieve_context", "retrieved", repo_id=state.repo_id, commit_id=req.commitId,
                details={"count": len(results), "ids": [r["file_path"] for r in results]})
        except Exception as e:
            log("retrieve_context", "fallback", repo_id=state.repo_id, commit_id=req.commitId,
                details={"error": str(e), "reliability_note": "embedding failed, using changed summaries only"})
            state.retrieved_context = []

    return state
