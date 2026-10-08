from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def make_settings(data_dir: Path) -> Settings:
    return Settings(data_dir=data_dir, port=0, max_upload_bytes=2 * 1024 * 1024,
                    backup_enabled=False, backup_keep_days=14, log_level="WARNING")


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(make_settings(data_dir)))


@pytest.fixture
def example_text() -> str:
    return (FIXTURES / "pelda.json").read_text(encoding="utf-8")


@pytest.fixture
def example(example_text: str) -> dict:
    return json.loads(example_text)


@pytest.fixture
def demo_text() -> str:
    return (EXAMPLES / "bemutato-naprendszer.json").read_text(encoding="utf-8")


def hdr(profile: dict) -> dict[str, str]:
    return {"X-Profile-Id": str(profile["id"])}


@pytest.fixture
def parent(client: TestClient) -> dict:
    r = client.post("/api/profiles", json={"name": "Anya", "role": "parent"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def child(client: TestClient, parent: dict) -> dict:
    r = client.post("/api/profiles", json={"name": "Bence", "role": "child"}, headers=hdr(parent))
    assert r.status_code == 201, r.text
    return r.json()
