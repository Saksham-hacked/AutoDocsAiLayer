from app.models import GraphState
from app.utils import log, build_repo_id
from app.observability import trace_node


async def validate_input(state: GraphState) -> GraphState:
    with trace_node("validate_input", {"repo": state.request.repo, "commit": state.request.commitId}):
        req = state.request
        if not req.changedFiles:
            state.error = "changedFiles is empty"
            state.skip_generation = True
            return state
        repo_id = build_repo_id(req.owner, req.repo)
        state.repo_id = repo_id
        log("validate_input", "validated", repo_id=repo_id, commit_id=req.commitId,
            details={"changed_files_count": len(req.changedFiles)})
    return state
