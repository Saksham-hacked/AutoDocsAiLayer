import time
import traceback
from fastapi import APIRouter, HTTPException, Header
from app.models import ProcessChangeRequest, ProcessChangeResponse
from app.langgraph_graph import graph
from app.models import GraphState
from app.config import get_settings
from app.utils import log, log_metric

router = APIRouter()
settings = get_settings()


def _check_secret(x_autodocs_secret: str = None):
    if x_autodocs_secret != settings.autodocs_shared_secret:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing X-AUTODOCS-SECRET")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/process-change", response_model=ProcessChangeResponse)
async def process_change(
    payload: ProcessChangeRequest,
    x_autodocs_secret: str = Header(None, alias="X-AUTODOCS-SECRET"),
):
    _check_secret(x_autodocs_secret)
    t0 = time.time()
    try:
        initial_state = GraphState(request=payload)
        result = await graph.ainvoke(initial_state)
        duration = (time.time() - t0) * 1000
        log_metric("commit_process_time_ms", duration, repo=payload.repo, commit=payload.commitId)

        # LangGraph ainvoke returns a plain dict — access with []
        return ProcessChangeResponse(
            files_to_update=result["generated_files"],
            pr_title=result["pr_title"],
            pr_body=result["pr_body"] or "No doc updates suggested.",
            confidence=result["overall_confidence"],
        )
    except Exception as e:
        tb = traceback.format_exc()
        log("api", "error", details={"error": str(e), "traceback": tb})
        print(tb)  # print to stdout so you can see it in the terminal
        raise HTTPException(status_code=500, detail={"error": str(e)})
