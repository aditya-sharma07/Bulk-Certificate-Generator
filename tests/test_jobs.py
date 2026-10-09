from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient


def test_create_generation_job(client: TestClient, valid_payload: dict) -> None:
    response = client.post("/api/v1/jobs", json=valid_payload)

    assert response.status_code == 202
    body = response.json()
    assert len(body["id"]) == 32
    assert body["status"] == "queued"
    assert body["total"] == 2
    assert body["status_url"] == f"/api/v1/jobs/{body['id']}"


def test_input_validation(client: TestClient, valid_payload: dict) -> None:
    empty = {**valid_payload, "recipients": []}
    invalid_email = {
        **valid_payload,
        "recipients": [{"name": "Ada", "email": "not-an-email"}],
    }
    blank_name = {**valid_payload, "recipients": [{"name": "   "}]}

    assert client.post("/api/v1/jobs", json=empty).status_code == 422
    assert client.post("/api/v1/jobs", json=invalid_email).status_code == 422
    assert client.post("/api/v1/jobs", json=blank_name).status_code == 422


def test_certificate_generation_and_job_progress(
    client: TestClient, valid_payload: dict
) -> None:
    created = client.post("/api/v1/jobs", json=valid_payload).json()
    response = client.get(created["status_url"])

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "completed"
    assert job["progress"] == {
        "total": 2,
        "queued": 0,
        "processing": 0,
        "succeeded": 2,
        "failed": 0,
        "percent_complete": 100.0,
    }
    assert all(item["status"] == "succeeded" for item in job["recipients"])
    assert all(item["download_url"] for item in job["recipients"])
    assert job["download_all_url"] is not None


def test_individual_failure_does_not_stop_job(
    client: TestClient, valid_payload: dict, monkeypatch
) -> None:
    from app.services import jobs

    real_generator = jobs.generate_certificate

    def generator_with_one_failure(*args, **kwargs):
        if kwargs["recipient"].name == "Ada Lovelace":
            raise RuntimeError("simulated rendering problem")
        return real_generator(*args, **kwargs)

    monkeypatch.setattr(jobs, "generate_certificate", generator_with_one_failure)
    created = client.post("/api/v1/jobs", json=valid_payload).json()
    job = client.get(created["status_url"]).json()

    assert job["status"] == "completed_with_errors"
    assert job["progress"]["succeeded"] == 1
    assert job["progress"]["failed"] == 1
    failed, succeeded = job["recipients"]
    assert failed["status"] == "failed"
    assert "simulated rendering problem" in failed["error"]
    assert failed["download_url"] is None
    assert succeeded["status"] == "succeeded"
    assert succeeded["download_url"] is not None


def test_retrieve_generated_certificate_and_zip(
    client: TestClient, valid_payload: dict
) -> None:
    created = client.post("/api/v1/jobs", json=valid_payload).json()
    job = client.get(created["status_url"]).json()

    pdf_response = client.get(job["recipients"][0]["download_url"])
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF")

    zip_response = client.get(job["download_all_url"])
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(zip_response.content)) as archive:
        names = archive.namelist()
        assert len(names) == 2
        assert all(name.endswith(".pdf") for name in names)
        assert all(archive.read(name).startswith(b"%PDF") for name in names)


def test_unknown_job_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/jobs/{'0' * 32}")
    assert response.status_code == 404

