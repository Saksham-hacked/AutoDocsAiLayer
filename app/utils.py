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
    # Strip ALL occurrences of managed notice if LLM already included it in the content
    import re
    clean_content = re.sub(r'<!--\s*Managed by AutoDocs v1[^>]*-->\s*', '', new_content).strip()
    start_idx = text.find(start_tag)
    end_idx = text.find(end_tag)
    if start_idx == -1 or end_idx == -1:
        return text + f"\n{start_tag}{managed_notice}{clean_content}\n{end_tag}\n"
    return text[:start_idx + len(start_tag)] + managed_notice + clean_content + "\n" + text[end_idx:]


def parse_llm_json(raw: str) -> dict:
    """
    Robustly parse JSON from LLM output.
    Handles: markdown fences, leading whitespace, embedded backtick code blocks
    inside string values (the most common LLM failure mode).
    """
    raw = raw.strip()

    # Strip outer markdown fence e.g. ```json ... ``` or ``` ... ```
    if raw.startswith("```"):
        lines = raw.split("\n")
        start_line = 1
        end_line = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        raw = "\n".join(lines[start_line:end_line]).strip()

    # Isolate the outermost JSON object
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError(f"No JSON object found in LLM output: {raw[:200]}")
    raw = raw[start:end]

    # Replace triple-backtick fences that the LLM embeds inside "content" values.
    # These break json.loads because backticks inside a JSON string are fine but
    # the LLM often forgets to escape newlines, producing unterminated strings.
    # We swap them out, parse, then restore in all string values.
    PLACEHOLDER = "__BACKTICK3__"
    raw_safe = raw.replace("```", PLACEHOLDER)

    parsed = json.loads(raw_safe)

    def restore(obj):
        if isinstance(obj, str):
            return obj.replace(PLACEHOLDER, "```")
        if isinstance(obj, dict):
            return {k: restore(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [restore(i) for i in obj]
        return obj

    return restore(parsed)


def build_repo_id(owner: str, repo: str) -> str:
    return f"{owner}/{repo}"
