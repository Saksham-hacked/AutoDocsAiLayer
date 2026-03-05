from app.models import GraphState
from app.utils import log
from app.observability import trace_node


async def confidence_check(state: GraphState) -> GraphState:
    if state.skip_generation:
        return state

    with trace_node("confidence_check", {}):
        review_required = False
        for f in state.generated_files:
            if f.confidence == "Low":
                review_required = True
            if "UNVERIFIED" in f.content:
                f.confidence = "Low"
                review_required = True

        # Downgrade overall if any file is low
        confidences = [f.confidence for f in state.generated_files]
        if "Low" in confidences:
            state.overall_confidence = "Low"
        elif "Medium" in confidences:
            state.overall_confidence = "Medium"
        else:
            state.overall_confidence = "High"

        if review_required:
            state.pr_body = (state.pr_body or "") + "\n\n⚠️ **review_required**: Some sections have Low confidence or UNVERIFIED statements."

        log("confidence_check", "done", repo_id=state.repo_id, details={
            "overall_confidence": state.overall_confidence, "review_required": review_required
        })

    return state
