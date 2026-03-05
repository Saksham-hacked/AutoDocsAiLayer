import pytest
from unittest.mock import AsyncMock, patch
from app.agents.classify_change import validate_input
from app.models import GraphState, ProcessChangeRequest


def make_request(**kwargs):
    defaults = dict(
        repo="test-repo", owner="acme", branch="main",
        installationId=1, commitMessage="test", commitId="abc123",
        changedFiles=["src/index.js"]
    )
    defaults.update(kwargs)
    return ProcessChangeRequest(**defaults)


@pytest.mark.asyncio
async def test_validate_input_sets_repo_id():
    state = GraphState(request=make_request())
    result = await validate_input(state)
    assert result.repo_id == "acme/test-repo"


@pytest.mark.asyncio
async def test_validate_input_empty_files():
    state = GraphState(request=make_request(changedFiles=[]))
    result = await validate_input(state)
    assert result.skip_generation is True
    assert result.error is not None
