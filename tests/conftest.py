from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    application = create_app(
        Settings(
            database_path=tmp_path / "test.db",
            storage_dir=tmp_path / "generated",
            max_recipients_per_job=10,
        )
    )
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def valid_payload() -> dict:
    return {
        "certificate": {
            "title": "Certificate of Completion",
            "course": "Practical FastAPI",
            "issuer": "Example Academy",
            "issue_date": "2026-10-08",
        },
        "recipients": [
            {"name": "Ada Lovelace", "email": "ada@example.com"},
            {"name": "Grace Hopper", "email": "grace@example.com"},
        ],
    }

