"""Substrate smoke test — proves the app imports and the verification command runs.

Feature tests (tax engine, W-2 parse, PDF fill, guardrails, ...) land in tests/ per
the FEATURES.md ledger.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
