import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(tempfile.gettempdir()) / "ainovel-regression.db").replace("\\", "/")
os.environ["SESSION_SECRET"] = "regression-only-session-secret-123456789"
os.environ["LLM_BASE_URL"] = "https://co.agentrouter.org/v1"
os.environ["LLM_API_KEY"] = "test-secret-not-real"

import pytest
from fastapi.testclient import TestClient

from app.auth import password_hash
from app.db import Base, engine
from app.main import app, login_attempts
from app.migrations import migrate


@pytest.fixture
def client(monkeypatch):
    Base.metadata.drop_all(engine)
    migrate(engine)
    login_attempts.clear()
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", password_hash("test-password", iterations=100000))
    monkeypatch.setattr("app.main.wake_worker", lambda: None)
    with TestClient(app) as instance:
        assert instance.post("/api/login", json={"password": "test-password"}).status_code == 200
        yield instance


@pytest.fixture
def novel(client):
    return client.post("/api/novels", json={"title": "药师", "premise": "药师追查古药与身世", "planned_chapters": 50}).json()
