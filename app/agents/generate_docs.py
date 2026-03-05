from app.models import GraphState, FileUpdate, SourceRef
from app.tools.layer1_client import Layer1Client
from app.tools.llm_client import LLMClient
from app.utils import log, parse_llm_json, extract_marker_content
from app.observability import trace_node
from pathlib import Path

_STYLE_GUIDE = (Path(__file__).parent.parent / "prompts" / "generate_doc_update.prompt.txt").read_text()


async def generate_docs(state: GraphState, layer1: Layer1Client = None, llm_client: LLMClient = None) -> GraphState:
    if state.skip_generation:
        return state

    layer1 = layer1 or Layer1Client()
    llm_client = llm_client or LLMClient()
    req = state.request
    target_docs = state.impact_result.get("target_docs", [])
    diffs = (req.optional.diffs if req.optional and req.optional.diffs else {})
    diff_text = "\n".join(diffs.values())[:3000]

    changed_summaries_text = "\n".join(
        f"FILE: {s['file_path']}\n{s['summary']}" for s in state.changed_summaries
    )
    retrieved_text = "\n".join(
        f"FILE: {r['file_path']} (score={r.get('score', 0):.2f})\n{r['summary']}" for r in state.retrieved_context
    )

    files_to_update = []

    with trace_node("generate_docs", {"target_docs": [t[0] for t in target_docs]}):
        for doc_path, marker_section in target_docs:
            try:
                doc_content = await layer1.fetch_file(doc_path, req.repo, req.owner, req.branch)
            except Exception:
                doc_content = ""

            existing_marker = extract_marker_content(doc_content, marker_section)

            user_msg = (
                f"Doc file: {doc_path}\nSection marker: {marker_section}\n"
                f"Existing marker content:\n{existing_marker}\n\n"
                f"Changed file summaries:\n{changed_summaries_text}\n\n"
                f"Retrieved context summaries:\n{retrieved_text}\n\n"
                f"Diff:\n{diff_text}\n\n"
                "Return ONLY valid JSON with keys: content (string), confidence (High|Medium|Low), "
                "sources (list of {path, lines, score})."
            )

            try:
                raw = await llm_client.complete(_STYLE_GUIDE, user_msg, temperature=0.1)
                parsed = parse_llm_json(raw)
                content = parsed.get("content", "")
                confidence = parsed.get("confidence", "Low")
                sources = [SourceRef(**s) for s in parsed.get("sources", [])]
            except Exception as e:
                log("generate_docs", "llm_error", repo_id=state.repo_id, commit_id=req.commitId,
                    details={"doc": doc_path, "error": str(e)})
                continue

            files_to_update.append(FileUpdate(
                path=doc_path, content=content, confidence=confidence, sources=sources
            ))
            log("generate_docs", "generated", repo_id=state.repo_id, commit_id=req.commitId,
                details={"doc": doc_path, "confidence": confidence})

    state.generated_files = files_to_update
    return state
