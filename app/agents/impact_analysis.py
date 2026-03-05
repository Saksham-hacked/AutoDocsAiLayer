import re
from typing import List, Dict, Any
from app.models import GraphState
from app.tools.llm_client import LLMClient
from app.utils import log, parse_llm_json
from app.observability import trace_node
from app.config import get_settings
from pathlib import Path

settings = get_settings()
_CLASSIFY_PROMPT = (Path(__file__).parent.parent / "prompts" / "classify_change.prompt.txt").read_text()

CHANGE_DOC_MAP = {
    "NEW_API_ROUTE": [("docs/api.md", "ROUTES")],
    "NEW_ENV_VARIABLE": [("docs/env.md", "ENV")],
    "DEPENDENCY_UPDATE": [("docs/setup.md", "INSTALL")],
    "FUNCTION_SIGNATURE_CHANGE": [("docs/api.md", "ROUTES")],
    "NEW_MODULE": [("docs/architecture.md", "MODULES")],
    "INTERNAL_REFACTOR": [],
    "COMMENT_ONLY": [],
}


def _rule_based_labels(changed_files: List[str], diffs: Dict[str, str]) -> List[str]:
    labels = set()
    diff_all = "\n".join(diffs.values()) if diffs else ""
    for path in changed_files:
        if re.search(r"package\.json|requirements\.txt|pyproject\.toml|setup\.cfg", path):
            labels.add("DEPENDENCY_UPDATE")
        if re.search(r"\.env|env\.example", path):
            labels.add("NEW_ENV_VARIABLE")
    if re.search(r"(app|router|route|api)\.(get|post|put|delete|patch)\s*\(", diff_all, re.IGNORECASE):
        labels.add("NEW_API_ROUTE")
    if re.search(r"^\+\s*(export\s+)?(async\s+)?function\s+\w+", diff_all, re.MULTILINE):
        labels.add("FUNCTION_SIGNATURE_CHANGE")
    if re.search(r"^\+\s*[A-Z_]{4,}\s*=", diff_all, re.MULTILINE):
        labels.add("NEW_ENV_VARIABLE")
    return list(labels)


async def impact_analysis(state: GraphState, llm_client: LLMClient = None) -> GraphState:
    if state.skip_generation:
        return state

    llm_client = llm_client or LLMClient()
    req = state.request
    diffs = (req.optional.diffs if req.optional and req.optional.diffs else {})

    rule_labels = _rule_based_labels(req.changedFiles, diffs)
    diff_snippet = "\n".join(list(diffs.values())[:3])[:2000]

    with trace_node("impact_analysis", {"commit": req.commitId, "rule_labels": rule_labels}):
        try:
            user_msg = (
                f"Changed files: {req.changedFiles}\n"
                f"Commit message: {req.commitMessage}\n"
                f"Diff snippet:\n{diff_snippet}\n"
                f"Rule-based labels found: {rule_labels}\n"
                "Return JSON with keys: labels (list), relevance_score (0-100), reasoning (string)."
            )
            raw = await llm_client.complete(_CLASSIFY_PROMPT, user_msg, temperature=0.0)
            parsed = parse_llm_json(raw)
            labels = list(set(rule_labels + parsed.get("labels", [])))
            relevance_score = parsed.get("relevance_score", 50)
            reasoning = parsed.get("reasoning", "")
        except Exception as e:
            labels = rule_labels
            relevance_score = 60 if rule_labels else 20
            reasoning = f"LLM classification failed: {e}"

        target_docs = []
        for label in labels:
            target_docs.extend(CHANGE_DOC_MAP.get(label, []))
        target_docs = list({t[0]: t for t in target_docs}.values())  # dedup by path

        state.impact_result = {
            "labels": labels,
            "relevance_score": relevance_score,
            "reasoning": reasoning,
            "target_docs": target_docs,
        }
        if relevance_score < settings.relevance_threshold or not target_docs:
            state.skip_generation = True

        log("impact_analysis", "done", repo_id=state.repo_id, commit_id=req.commitId,
            details={"labels": labels, "relevance_score": relevance_score, "target_docs": target_docs})

    return state
