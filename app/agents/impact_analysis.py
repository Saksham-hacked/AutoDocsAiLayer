import re
from typing import List, Dict
from app.models import GraphState
from app.tools.llm_client import LLMClient
from app.utils import log, parse_llm_json
from app.observability import trace_node
from app.config import get_settings
from pathlib import Path

settings = get_settings()
_CLASSIFY_PROMPT = (Path(__file__).parent.parent / "prompts" / "classify_change.prompt.txt").read_text()

CHANGE_DOC_MAP = {
    "NEW_API_ROUTE":             [("docs/api.md", "ROUTES")],
    "NEW_ENV_VARIABLE":          [("docs/env.md", "ENV")],
    "DEPENDENCY_UPDATE":         [("docs/setup.md", "INSTALL")],
    "FUNCTION_SIGNATURE_CHANGE": [("docs/api.md", "ROUTES")],
    "NEW_MODULE":                [("docs/architecture.md", "MODULES")],
    "INTERNAL_REFACTOR":         [("docs/architecture.md", "MODULES")],
    "COMMENT_ONLY":              [],
}


def _rule_based_labels(changed_files: List[str], diffs: Dict[str, str]) -> List[str]:
    labels = set()
    diff_all = "\n".join(diffs.values()) if diffs else ""

    for path in changed_files:
        if re.search(r"package\.json|requirements\.txt|pyproject\.toml|setup\.cfg", path):
            labels.add("DEPENDENCY_UPDATE")
        if re.search(r"\.env($|\.example)", path):
            labels.add("NEW_ENV_VARIABLE")
        if re.search(r"(model|schema|entity|struct)s?[/\\].*\.(js|ts|py|go|java)$", path, re.IGNORECASE):
            labels.add("NEW_MODULE")

    if re.search(r"(app|router|route|api)\s*\.\s*(get|post|put|delete|patch)\s*\(", diff_all, re.IGNORECASE):
        labels.add("NEW_API_ROUTE")
    # also catch express-style: router.get('/path', ...)
    if re.search(r"router\s*\.\s*(get|post|put|delete|patch)\s*\(", diff_all, re.IGNORECASE):
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
    diffs = req.optional.diffs if req.optional and req.optional.diffs else {}

    rule_labels = _rule_based_labels(req.changedFiles, diffs)
    diff_snippet = "\n".join(list(diffs.values())[:3])[:10000]

    log("impact_analysis", "rule_labels", repo_id=state.repo_id, commit_id=req.commitId,
        details={"rule_labels": rule_labels})

    with trace_node("impact_analysis", {"commit": req.commitId, "rule_labels": rule_labels}):
        llm_labels = []
        llm_score = None
        reasoning = ""

        try:
            user_msg = (
                f"Changed files: {req.changedFiles}\n"
                f"Commit message: {req.commitMessage}\n"
                f"Diff snippet:\n{diff_snippet}\n"
                f"Rule-based labels found: {rule_labels}\n"
                "Return JSON with keys: labels (list), relevance_score (0-100), reasoning (string)."
            )
            raw = await llm_client.complete(_CLASSIFY_PROMPT, user_msg, temperature=0.0)
            log("impact_analysis", "llm_raw", repo_id=state.repo_id, commit_id=req.commitId,
                details={"raw": raw[:300]})
            parsed = parse_llm_json(raw)
            llm_labels = parsed.get("labels", [])
            llm_score = parsed.get("relevance_score")
            reasoning = parsed.get("reasoning", "")
        except Exception as e:
            log("impact_analysis", "llm_failed", repo_id=state.repo_id, commit_id=req.commitId,
                details={"error": str(e)})

        # Merge rule labels + LLM labels
        labels = list(set(rule_labels + llm_labels))

        # Score: use LLM score if provided and reasonable, otherwise derive from rule labels
        if llm_score is not None and 0 <= llm_score <= 100:
            relevance_score = llm_score
        elif rule_labels:
            # We found clear rule-based signals — set score high enough to pass threshold
            relevance_score = 80
        else:
            relevance_score = 20

        # If rule labels found doc-relevant changes, never let LLM score suppress them
        doc_relevant_rules = [l for l in rule_labels if CHANGE_DOC_MAP.get(l)]
        if doc_relevant_rules and relevance_score < settings.relevance_threshold:
            log("impact_analysis", "score_override", repo_id=state.repo_id, commit_id=req.commitId,
                details={"old_score": relevance_score, "new_score": 80, "reason": "rule labels override"})
            relevance_score = 80

        # Map labels to target doc files
        target_docs = []
        for label in labels:
            target_docs.extend(CHANGE_DOC_MAP.get(label, []))
        # Dedup by doc path, keeping first occurrence
        seen = set()
        deduped = []
        for item in target_docs:
            if item[0] not in seen:
                seen.add(item[0])
                deduped.append(item)
        target_docs = deduped

        state.impact_result = {
            "labels": labels,
            "relevance_score": relevance_score,
            "reasoning": reasoning,
            "target_docs": target_docs,
        }

        if relevance_score < settings.relevance_threshold or not target_docs:
            state.skip_generation = True
            log("impact_analysis", "skip", repo_id=state.repo_id, commit_id=req.commitId,
                details={"reason": "low score or no target docs", "score": relevance_score, "target_docs": target_docs})
        else:
            log("impact_analysis", "will_generate", repo_id=state.repo_id, commit_id=req.commitId,
                details={"labels": labels, "relevance_score": relevance_score, "target_docs": target_docs})

    return state
