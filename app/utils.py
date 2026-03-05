import json
import logging
import time
from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
_logger = logging.getLogger("autodocs")


def log(node: str, event: str, repo_id: str = "", commit_id: str = "", duration_ms: float = 0, details: dict = None):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_id": repo_id,
        "commit_id": commit_id,
        "node": node,
        "event": event,
        "duration_ms": round(duration_ms, 2),
        "details": details or {},
    }
    _logger.info(json.dumps(record))


def log_metric(metric: str, value: float, repo: str = "", commit: str = ""):
    print(json.dumps({"metric": metric, "value": value, "repo": repo, "commit": commit}))


def extract_marker_content(text: str, section: str) -> str:
    """Extract content between AUTODOCS marker tags."""
    start_tag = f"<!-- AUTODOCS:{section}_START -->"
    end_tag = f"<!-- AUTODOCS:{section}_END -->"
    start_idx = text.find(start_tag)
    end_idx = text.find(end_tag)
    if start_idx == -1 or end_idx == -1:
        return ""
    return text[start_idx + len(start_tag):end_idx]


def replace_marker_content(text: str, section: str, new_content: str) -> str:
    """Replace content between AUTODOCS marker tags."""
    start_tag = f"<!-- AUTODOCS:{section}_START -->"
    end_tag = f"<!-- AUTODOCS:{section}_END -->"
    managed_notice = "\n<!-- Managed by AutoDocs v1 — Changes may be overwritten -->\n"
    start_idx = text.find(start_tag)
    end_idx = text.find(end_tag)
    if start_idx == -1 or end_idx == -1:
        return text + f"\n{start_tag}{managed_notice}{new_content}\n{end_tag}\n"
    return text[:start_idx + len(start_tag)] + managed_notice + new_content + "\n" + text[end_idx:]


def parse_llm_json(raw: str) -> dict:
    """Robustly parse JSON from LLM output, stripping markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # fallback: find first { ... }
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])
        raise


def build_repo_id(owner: str, repo: str) -> str:
    return f"{owner}/{repo}"
