import pytest
from app.utils import extract_marker_content, replace_marker_content, parse_llm_json


def test_marker_extraction():
    text = "before\n<!-- AUTODOCS:ROUTES_START -->\nsome content\n<!-- AUTODOCS:ROUTES_END -->\nafter"
    result = extract_marker_content(text, "ROUTES")
    assert "some content" in result


def test_marker_replacement():
    text = "before\n<!-- AUTODOCS:ROUTES_START -->\nold\n<!-- AUTODOCS:ROUTES_END -->\nafter"
    result = replace_marker_content(text, "ROUTES", "new content")
    assert "new content" in result
    assert "old" not in result
    assert "before" in result
    assert "after" in result


def test_marker_insert_when_missing():
    text = "# Docs\nsome text"
    result = replace_marker_content(text, "ROUTES", "inserted content")
    assert "inserted content" in result
    assert "AUTODOCS:ROUTES_START" in result


def test_parse_llm_json_clean():
    raw = '{"labels": ["NEW_API_ROUTE"], "relevance_score": 85, "reasoning": "adds route"}'
    parsed = parse_llm_json(raw)
    assert parsed["relevance_score"] == 85


def test_parse_llm_json_with_fences():
    raw = '```json\n{"content": "hello", "confidence": "High", "sources": []}\n```'
    parsed = parse_llm_json(raw)
    assert parsed["confidence"] == "High"
