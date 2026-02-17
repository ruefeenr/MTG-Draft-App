import json
import os
import random
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.db import db


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key")
    yield tmp_path


@pytest.fixture
def app(isolated_workspace):
    test_app = create_app()
    test_app.config["TESTING"] = True
    with test_app.app_context():
        db.create_all()
    yield test_app
    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded_random():
    random.seed(42)
    return 42


@pytest.fixture
def golden_fixtures():
    base_dir = os.path.join(os.path.dirname(__file__), "fixtures")

    def _load(name):
        path = os.path.join(base_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    return _load
