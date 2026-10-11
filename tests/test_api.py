from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def app(tmp_path: Path):
    return create_app(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        storage_dir=tmp_path / "certificates",
    )


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def request_body(recipients=None):
    return {
        "certificate": {
            "certificate_title": "Certificate of Completion",
            "event_name": "Backend Engineering Workshop",
            "issuer": "Example Institute",
            "issue_date": "2026-10-11",
        },
        "recipients": recipients
        if recipients is not None
        else [{"name": "Ada Lovelace", "email": "ada@example.com"}],
    }


def create_job(client: TestClient, recipients=None) -> dict:
    response = client.post("/api/v1/jobs", json=request_body(recipients))
    assert response.status_code == 202
    return response.json()


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_job_and_persist_completed_progress(client):
    created = create_job(
        client,
        [{"name": "Ada Lovelace"}, {"name": "Grace Hopper", "email": "grace@example.com"}],
    )
    assert created["status"] == "queued"
    assert created["total_count"] == 2
    assert created["progress_percent"] == 0

    status_response = client.get(f"/api/v1/jobs/{created['job_id']}")
    assert status_response.status_code == 200
    result = status_response.json()
    assert result["status"] == "completed"
    assert result["processed_count"] == 2
    assert result["success_count"] == 2
    assert result["failure_count"] == 0
    assert result["progress_percent"] == 100


@pytest.mark.parametrize(
    "body",
    [
        {"certificate": {}, "recipients": [{"name": "Ada"}]},
        {
            **request_body([]),
            "certificate": {
                "certificate_title": "Title",
                "event_name": "Event",
                "issuer": "Issuer",
                "issue_date": "not-a-date",
            },
        },
        request_body([]),
        {**request_body(), "unexpected": True},
        {**request_body(), "recipients": ["not an object"]},
    ],
)
def test_request_validation_rejects_invalid_payloads(client, body):
    response = client.post("/api/v1/jobs", json=body)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_malformed_recipient_is_failed_without_rejecting_the_job(client):
    created = create_job(client, [{"name": 23}, {"name": "Valid Recipient"}])

    job = client.get(f"/api/v1/jobs/{created['job_id']}").json()
    assert job["status"] == "completed"
    assert job["success_count"] == 1
    assert job["failure_count"] == 1

    results = client.get(f"/api/v1/jobs/{created['job_id']}/results").json()["results"]
    assert [result["status"] for result in results].count("failed") == 1
    failure = next(result for result in results if result["status"] == "failed")
    assert failure["certificate_url"] is None
    assert failure["failure_reason"]


def test_certificate_is_a_pdf_and_can_be_downloaded(client):
    created = create_job(client)
    results = client.get(f"/api/v1/jobs/{created['job_id']}/results")
    assert results.status_code == 200
    result = results.json()["results"][0]
    assert result["name"] == "Ada Lovelace"
    assert result["status"] == "succeeded"

    download = client.get(result["certificate_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF-")
    assert len(download.content) > 500


def test_one_generation_error_does_not_stop_other_recipients(client, monkeypatch):
    from app import processing

    original_generate = processing.generate_certificate

    def fail_one_recipient(path, recipient, certificate):
        if recipient.name == "Broken Recipient":
            raise RuntimeError("simulated PDF failure")
        original_generate(path, recipient, certificate)

    monkeypatch.setattr(processing, "generate_certificate", fail_one_recipient)
    created = create_job(
        client,
        [{"name": "Broken Recipient"}, {"name": "Working Recipient"}],
    )

    job = client.get(f"/api/v1/jobs/{created['job_id']}").json()
    results = client.get(f"/api/v1/jobs/{created['job_id']}/results").json()["results"]
    assert job["status"] == "completed"
    assert (job["success_count"], job["failure_count"]) == (1, 1)
    assert [result["status"] for result in results] == ["failed", "succeeded"]


def test_missing_jobs_and_recipients_return_404(client):
    missing_job = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/v1/jobs/{missing_job}").status_code == 404
    assert client.get(f"/api/v1/jobs/{missing_job}/results").status_code == 404
    assert (
        client.get(
            f"/api/v1/jobs/{missing_job}/certificates/00000000-0000-0000-0000-000000000001"
        ).status_code
        == 404
    )


def test_missing_generated_file_returns_404(client, app):
    created = create_job(client)
    result = client.get(f"/api/v1/jobs/{created['job_id']}/results").json()["results"][0]
    certificate_path = app.state.storage_dir / created["job_id"] / f"{result['recipient_id']}.pdf"
    certificate_path.unlink()

    response = client.get(result["certificate_url"])
    assert response.status_code == 404
    assert response.json()["detail"] == "Certificate file not found"


def test_jobs_and_certificates_survive_application_restart(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'persistent.db'}"
    storage_dir = tmp_path / "persistent-certificates"
    first_app = create_app(database_url=database_url, storage_dir=storage_dir)

    with TestClient(first_app) as first_client:
        created = create_job(first_client)
        result = first_client.get(
            f"/api/v1/jobs/{created['job_id']}/results"
        ).json()["results"][0]

    restarted_app = create_app(database_url=database_url, storage_dir=storage_dir)
    with TestClient(restarted_app) as restarted_client:
        job = restarted_client.get(f"/api/v1/jobs/{created['job_id']}").json()
        download = restarted_client.get(result["certificate_url"])

    assert job["status"] == "completed"
    assert job["success_count"] == 1
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")
