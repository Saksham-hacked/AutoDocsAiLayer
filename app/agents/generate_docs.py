from app.models import GraphState, FileUpdate, SourceRef
from app.tools.layer1_client import Layer1Client
from app.tools.llm_client import LLMClient
from app.utils import log, parse_llm_json, extract_marker_content
from app.observability import trace_node
from pathlib import Path

_STYLE_GUIDE = (Path(__file__).parent.parent / "prompts" / "generate_doc_update.prompt.txt").read_text()


async def generate_docs(
    state: GraphState,
    layer1: Layer1Client = None,
    llm_client: LLMClient = None,
) -> GraphState:
    if state.skip_generation:
        log("generate_docs", "skipped", repo_id=state.repo_id, commit_id=state.request.commitId)
        return state

    layer1 = layer1 or Layer1Client()
    llm_client = llm_client or LLMClient()
    req = state.request
    target_docs = state.impact_result.get("target_docs", [])

    log("generate_docs", "start", repo_id=state.repo_id, commit_id=req.commitId,
        details={"target_docs": target_docs, "changed_summaries": len(state.changed_summaries),
                 "retrieved_context": len(state.retrieved_context)})

    diffs = req.optional.diffs if req.optional and req.optional.diffs else {}
    diff_text = "\n".join(diffs.values())[:20000]

    changed_summaries_text = "\n".join(
        f"FILE: {s['file_path']}\n{s['summary']}" for s in state.changed_summaries
    )
    retrieved_text = "\n".join(
        f"FILE: {r['file_path']} (score={r.get('score', 0):.2f})\n{r['summary']}"
        for r in state.retrieved_context
    )

    files_to_update = []

    with trace_node("generate_docs", {"target_docs": [t[0] for t in target_docs]}):
        for doc_path, marker_section in target_docs:
            # Fetch existing doc — fall back to empty string if Layer1 unavailable
            doc_content = ""
            try:
                doc_content = await layer1.fetch_file(doc_path, req.repo, req.owner, req.branch, req.installationId)
            except Exception as e:
                log("generate_docs", "doc_fetch_failed", repo_id=state.repo_id,
                    commit_id=req.commitId, details={"doc": doc_path, "error": str(e)})

            existing_marker = extract_marker_content(doc_content, marker_section)

            existing = existing_marker.strip() if existing_marker and existing_marker.strip() else ""
            user_msg = (
                f"Doc file: {doc_path}\nSection marker: {marker_section}\n\n"
                f"Current section content (copy this into your output unchanged, then append new entries):\n"
                f"{existing if existing else '(empty)'}\n\n"
                f"What changed in this commit:\n"
                f"Summaries: {changed_summaries_text or '(none)'}\n"
                f"Diff: {diff_text or '(none)'}\n"
                f"Retrieved context: {retrieved_text or '(none)'}\n\n"
                "Return ONLY valid JSON with keys: content (string), confidence (High|Medium|Low), "
                "sources (list of {path, lines, score})."
            )

            try:
                raw = await llm_client.complete(_STYLE_GUIDE, user_msg, temperature=0.1)
                log("generate_docs", "llm_raw", repo_id=state.repo_id, commit_id=req.commitId,
                    details={"doc": doc_path, "raw_preview": raw[:200]})
                parsed = parse_llm_json(raw)
                content = parsed.get("content", "")
                confidence = parsed.get("confidence", "Low")
                sources = []
                for s in parsed.get("sources", []):
                    try:
                        sources.append(SourceRef(**s))
                    except Exception:
                        pass
            except Exception as e:
                log("generate_docs", "llm_error", repo_id=state.repo_id, commit_id=req.commitId,
                    details={"doc": doc_path, "error": str(e)})
                continue

            files_to_update.append(FileUpdate(
                path=doc_path,
                content=content,
                confidence=confidence,
                sources=sources,
                marker_section=marker_section,
            ))
            log("generate_docs", "generated", repo_id=state.repo_id, commit_id=req.commitId,
                details={"doc": doc_path, "confidence": confidence, "content_len": len(content)})

    state.generated_files = files_to_update
    log("generate_docs", "complete", repo_id=state.repo_id, commit_id=req.commitId,
        details={"files_generated": len(files_to_update)})
    return state
