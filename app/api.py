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


# ── Endpoints that Layer 2 calls back into Layer 1 for ──────────────────────
# These are STUB endpoints on Layer 2 itself — in production Layer 1 (Node.js)
# implements these. They are provided here so Layer 2 can be tested standalone.

@router.get("/files/file-content")
async def file_content(
    path: str,
    repo: str,
    owner: str,
    branch: str,
    x_autodocs_secret: str = Header(None, alias="X-AUTODOCS-SECRET"),
):
    _check_secret(x_autodocs_secret)
    # Stub: return empty. Real implementation lives in Layer 1 (Node.js).
    return {"content": ""}


@router.get("/files/file-diff")
async def file_diff(
    path: str,
    repo: str,
    owner: str,
    branch: str,
    commit_id: str = "",
    x_autodocs_secret: str = Header(None, alias="X-AUTODOCS-SECRET"),
):
    _check_secret(x_autodocs_secret)
    return {"diff": ""}


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
