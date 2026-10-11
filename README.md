# Bulk Certificate Generator

A backend-only REST API built with **Python, FastAPI, SQLAlchemy, SQLite, and ReportLab** to generate PDF certificates in bulk.

## Overview

The service accepts a single request containing certificate information and multiple recipients. It validates recipient data, generates individual PDF certificates using a predefined template, stores job and recipient results in a relational database, and exposes APIs for tracking progress and retrieving generated certificates.

## Features

- Bulk certificate-generation requests
- Recipient-level input validation
- PDF generation using a predefined template
- SQL persistence for jobs and generation results
- Job status and progress tracking
- Independent handling of individual certificate failures
- Certificate retrieval through REST endpoints
- Interactive API documentation with Swagger UI
- Automated tests using Pytest

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming language |
| FastAPI | REST API framework |
| SQLAlchemy | Database ORM |
| SQLite | Relational database |
| ReportLab | PDF certificate generation |
| Pytest | Automated testing |

## Quick Start

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Start the application:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to explore and test the API.

## Testing

Run the automated test suite:

```bash
python -m pytest -v
```

## Design Notes

Generation jobs and recipient-level outcomes are stored in SQLite. Generated PDF files are stored on disk, with their locations recorded in the database.

Processing uses FastAPI in-process background tasks. This is suitable for the assignment's basic workflow but does not provide durable queue processing or automatic recovery after a process interruption.

See the API documentation and the remainder of this README for request examples, endpoint details, setup instructions, and implementation decisions.
