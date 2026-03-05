#!/bin/bash
set -e
cp .env.example .env 2>/dev/null || true
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
