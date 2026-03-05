#!/usr/bin/env python3
"""Simulate a commit payload against the running AutoDocs Layer2 service."""
import json
import sys
import httpx

BASE_URL = "http://localhost:8080"
SECRET = "changeme"

if __name__ == "__main__":
    fixture = "tests/fixtures/new_route_payload.json"
    if len(sys.argv) > 1:
        fixture = sys.argv[1]

    with open(fixture) as f:
        payload = json.load(f)

    r = httpx.post(
        f"{BASE_URL}/process-change",
        json=payload,
        headers={"X-AUTODOCS-SECRET": SECRET},
        timeout=60,
    )
    print(f"Status: {r.status_code}")
    print(json.dumps(r.json(), indent=2))
