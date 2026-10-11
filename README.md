# Bulk Certificate Generator

A small FastAPI service that accepts one bulk request, validates recipients individually, and generates one PDF per valid recipient using a single built-in certificate design. Jobs, recipient outcomes, and file locations are stored in SQLite; generated PDFs are stored on disk.

## Requirements

- Python 3.10 or later
- pip

## Setup and run

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. FastAPI's interactive Swagger UI is at `/docs`, with the OpenAPI schema at `/openapi.json`.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./certificates.db` | SQLAlchemy database URL. SQLite is the supported relational database for this assignment. |
| `CERTIFICATE_STORAGE_DIR` | `./generated_certificates` | Directory in which generated PDFs are stored. |

The default relative paths are resolved from the process's current working directory. `.env` is an example for reference; the application reads environment variables and does not parse `.env` automatically. Set variables in the shell or use a dotenv loader externally if desired.

## API

### Health check

`GET /health`

```json
{"status": "ok"}
```

### Submit a bulk generation job

`POST /api/v1/jobs` returns `202 Accepted`. Each recipient must be a JSON object, but fields within each recipient are validated independently so one bad recipient is reported as a failed result without rejecting valid recipients in the same batch.

```json
{
  "certificate": {
    "certificate_title": "Certificate of Completion",
    "event_name": "Backend Engineering Workshop",
    "issuer": "Example Institute",
    "issue_date": "2026-10-11"
  },
  "recipients": [
    {"name": "Ada Lovelace", "email": "ada@example.com"},
    {"name": "Grace Hopper"}
  ]
}
```

The accepted response includes the generated job ID, initial `queued` status, recipient totals, zero initial progress, and timestamps:

```json
{
  "job_id": "56d31fa7-f1b1-4bdc-8417-836319da37c3",
  "status": "queued",
  "total_count": 2,
  "success_count": 0,
  "failure_count": 0,
  "processed_count": 0,
  "progress_percent": 0.0,
  "error_message": null,
  "created_at": "2026-10-11T12:00:00",
  "updated_at": "2026-10-11T12:00:00"
}
```

An empty recipient list, invalid certificate details, unknown top-level fields, or a non-object recipient entry returns `422 Unprocessable Entity`. A recipient object with missing or invalid fields is retained as an individual failed result.

### Retrieve job status and progress

`GET /api/v1/jobs/{job_id}` returns `total_count`, `success_count`, `failure_count`, `processed_count`, and `progress_percent`.

Job states are `queued`, `processing`, `completed`, and `failed`. A job with a mix of successful and failed recipients is `completed`; recipient failures do not fail the whole job. `failed` indicates an unexpected job-level processing error. Missing jobs return `404 Not Found`.

### Retrieve recipient results

`GET /api/v1/jobs/{job_id}/results` returns every recipient's status, name/email when available, failure details, and a download URL for successful certificates. Recipient states are `pending`, `succeeded`, and `failed`.

### Download a certificate

`GET /api/v1/jobs/{job_id}/certificates/{recipient_id}` returns the PDF attachment for a successful recipient. Unavailable, failed, missing, or deleted certificate files return `404 Not Found`.

## Persistence and processing

- SQLAlchemy creates `generation_jobs` and `generation_results` tables on application startup. Each result references its parent job with a foreign key. Job totals/status and recipient-level inputs, outcomes, failure details, timestamps, and certificate file paths persist in SQLite.
- The default database is `certificates.db`; generated certificates are stored under `generated_certificates/{job_id}/{recipient_id}.pdf`. Files use generated UUIDs rather than user-provided names, and downloads additionally verify that the stored path remains under the configured certificate directory.
- Each recipient is validated and generated independently. A failure is stored with a reason, and later recipients continue to be processed. Counts are refreshed and committed after each recipient.
- Processing uses FastAPI in-process `BackgroundTasks`: submission immediately persists the queued job, and processing is scheduled after the response. This is a deliberate low-dependency choice for the assignment. It is **not** a durable queue: a process crash or restart during processing can leave a job queued/processing, and there is no automatic recovery, retry, or multi-worker coordination. Use one application process for reliable assignment-scale operation.
- Job/result rows and PDF files remain available across restarts as long as the configured database and storage directory remain available. Database and filesystem writes are not one atomic transaction; an unexpected failure between them may require manual cleanup.

## Tests

```powershell
python -m pytest -v
```

Tests create a fresh SQLite database and PDF directory under pytest's temporary directory for each test. They cover health, bulk job creation, request and recipient validation, generated/downloadable PDFs, progress/results, per-recipient failures, missing jobs, empty batches, and missing files.
