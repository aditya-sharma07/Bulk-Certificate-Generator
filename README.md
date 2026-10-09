# Bulk Certificate Generator (FastAPI)

A backend API that accepts one request containing many recipients, generates a
PDF certificate for each recipient, records per-recipient results, and exposes
individual PDF and bulk ZIP downloads.

## Features

- Bulk job submission (up to 1,000 recipients by default)
- Strict request validation with useful FastAPI/Pydantic error responses
- Background PDF generation using one predefined certificate design
- Durable job and recipient status in SQLite
- Failure isolation: one rendering failure does not stop other recipients
- Job progress, per-recipient errors, individual PDF downloads, and ZIP download
- Interactive OpenAPI documentation at `/docs`

## Setup

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configuration is read from environment variables. The defaults work locally:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_PATH` | `data/certificates.db` | SQLite database file |
| `STORAGE_DIR` | `data/generated` | Generated PDF/ZIP directory |
| `MAX_RECIPIENTS_PER_JOB` | `1000` | Submission size limit |

See `.env.example` for the same values. The application does not load `.env`
automatically; set variables in the shell or use your preferred environment
loader.

## Run the application

```powershell
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> to use the API interactively. A health check is
available at `GET /health`.

## Submit a generation request

```powershell
$body = @{
  certificate = @{
    title = "Certificate of Completion"
    course = "Practical FastAPI"
    issuer = "Example Academy"
    issue_date = "2026-10-08"
  }
  recipients = @(
    @{ name = "Ada Lovelace"; email = "ada@example.com" },
    @{ name = "Grace Hopper"; email = "grace@example.com" }
  )
} | ConvertTo-Json -Depth 4

$job = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/jobs `
  -ContentType application/json `
  -Body $body

$job
```

The API responds with HTTP `202 Accepted`:

```json
{
  "id": "a-32-character-job-id",
  "status": "queued",
  "total": 2,
  "status_url": "/api/v1/jobs/a-32-character-job-id"
}
```

The ID in a real response is exactly 32 hexadecimal characters.

## Check status and retrieve certificates

Get job progress and per-recipient results:

```powershell
$result = Invoke-RestMethod `
  -Uri ("http://127.0.0.1:8000" + $job.status_url)
$result.progress
$result.recipients
```

The job status is one of `queued`, `processing`, `completed`,
`completed_with_errors`, or `failed`. Each recipient has `queued`, `processing`,
`succeeded`, or `failed` status. Successful entries include a `download_url`;
failed entries include an `error`.

Download one certificate using the URL returned for that recipient:

```powershell
Invoke-WebRequest `
  -Uri ("http://127.0.0.1:8000" + $result.recipients[0].download_url) `
  -OutFile certificate.pdf
```

Download all successful certificates as a ZIP using `download_all_url`:

```powershell
Invoke-WebRequest `
  -Uri ("http://127.0.0.1:8000" + $result.download_all_url) `
  -OutFile certificates.zip
```

## Run tests

```powershell
pytest
```

The suite covers job creation, request validation, certificate generation,
progress reporting, per-certificate failure isolation, and PDF/ZIP retrieval.
Tests use isolated temporary databases and storage directories.

## Design decisions

**Background processing.** FastAPI `BackgroundTasks` keeps the API simple and
returns `202` before generation work begins. This is a good fit for a compact
assignment and a single application process. The database remains the source of
truth for job progress, and each recipient is committed independently. For a
larger production deployment, the `process_job` function is already a clear unit
to move to a durable queue such as Celery/RQ with Redis, including retries and
worker monitoring. FastAPI background tasks themselves are not durable if the
process stops.

**Relational persistence.** SQLite stores a `jobs` row and child `recipients`
rows. Foreign keys preserve the relationship, while WAL mode and short
transactions allow status reads during processing. Production scale could swap
the small repository for PostgreSQL without changing the HTTP contract.

**Failure isolation.** Generation is wrapped per recipient. A failed PDF records
a bounded error message and processing continues. Final status is `completed`,
`completed_with_errors`, or `failed` based on aggregate results.

**File safety.** User names are never used as filesystem paths. PDFs are named
with generated IDs, written to a temporary file, and atomically moved into place.
ZIP entries also use generated IDs.

**Validation.** Pydantic validates required text, lengths, dates, recipient count,
and email shape before a job is created. The maximum recipient count is checked
against configuration. Invalid submissions receive HTTP 422 and create no job.

## Project structure

```text
app/
  api/routes.py             HTTP endpoints
  services/certificates.py PDF template renderer
  services/jobs.py         Job creation and processing
  config.py                 Environment configuration
  database.py               SQLite schema/repository helpers
  schemas.py                Request/response validation
  main.py                   FastAPI application factory
tests/                      API and failure-isolation tests
```

