import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SECRET = "changeme"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200


def test_missing_secret():
    r = client.post("/process-change", json={
        "repo": "r", "owner": "o", "branch": "main",
        "installationId": 1, "commitMessage": "m", "commitId": "abc",
        "changedFiles": ["f.py"]
    })
    assert r.status_code == 401


def test_wrong_secret():
    r = client.post("/process-change",
        json={"repo": "r", "owner": "o", "branch": "main",
              "installationId": 1, "commitMessage": "m", "commitId": "abc",
              "changedFiles": ["f.py"]},
        headers={"X-AUTODOCS-SECRET": "wrong"}
    )
    assert r.status_code == 401
