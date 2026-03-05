import time
from contextlib import contextmanager
from app.config import get_settings

settings = get_settings()

_langsmith_client = None


def _get_client():
    global _langsmith_client
    if _langsmith_client is None and settings.enable_langsmith and settings.langsmith_api_key:
        try:
            from langsmith import Client
            import os
            os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
            _langsmith_client = Client()
        except Exception:
            pass
    return _langsmith_client


@contextmanager
def trace_node(run_name: str, inputs: dict = None, parent_run_id=None):
    """Context manager that traces a node in LangSmith if enabled, else no-op."""
    client = _get_client()
    run_id = None
    start = time.time()
    if client:
        try:
            from langsmith.run_helpers import traceable
            run = client.create_run(
                name=run_name,
                inputs=_mask_secrets(inputs or {}),
                run_type="chain",
                parent_run_id=parent_run_id,
                project_name=settings.langsmith_project,
            )
            run_id = run.id if hasattr(run, "id") else None
        except Exception:
            pass
    try:
        yield run_id
    finally:
        duration = (time.time() - start) * 1000
        if client and run_id:
            try:
                client.update_run(run_id, end_time=None)
            except Exception:
                pass


def _mask_secrets(data: dict) -> dict:
    """Remove sensitive keys from trace data."""
    sensitive = {"secret", "token", "password", "api_key", "authorization"}
    return {k: ("***" if any(s in k.lower() for s in sensitive) else v) for k, v in data.items()}
