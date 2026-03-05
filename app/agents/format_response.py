from app.models import GraphState
from app.utils import log
from app.observability import trace_node


async def format_response(state: GraphState) -> GraphState:
    with trace_node("format_response", {}):
        req = state.request
        short_commit = req.commitId[:7]

        if state.skip_generation or not state.generated_files:
            state.pr_title = None
            state.pr_body = "No doc updates suggested."
            state.overall_confidence = None
            return state

        labels = state.impact_result.get("labels", [])
        label_str = ", ".join(labels) if labels else "changes"
        state.pr_title = f"📝 AutoDocs: {label_str} ({short_commit})"

        doc_list = "\n".join(f"- `{f.path}` ({f.confidence})" for f in state.generated_files)
        state.pr_body = (
            f"Automated documentation updates for commit `{req.commitId}`.\n\n"
            f"**Updated docs:**\n{doc_list}\n\n"
            f"**Overall confidence:** {state.overall_confidence}\n"
        )
        if state.pr_body and "review_required" in state.pr_body:
            pass  # already appended by confidence node

        log("format_response", "done", repo_id=state.repo_id, commit_id=req.commitId,
            details={"pr_title": state.pr_title, "files_updated": len(state.generated_files)})

    return state
