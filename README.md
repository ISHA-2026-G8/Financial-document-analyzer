# Financial Document Analyzer

Production-style asynchronous PDF analysis API. Upload a financial PDF, receive a `job_id` immediately, and let Redis/Celery workers process analysis in the background.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat&logo=fastapi&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.x-37814A?style=flat&logo=celery&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.x-DC382D?style=flat&logo=redis&logoColor=white)
![CrewAI](https://img.shields.io/badge/CrewAI-LLM%20Orchestration-6366F1?style=flat)

## Overview

This service is non-blocking by design:
- `POST /analyze` queues a job.
- `GET /jobs/{job_id}` returns job state and result.
- `/docs` provides Swagger UI.

## Tech Stack

| Layer | Tooling |
|---|---|
| API | FastAPI + Uvicorn |
| Queue | Celery + Redis |
| LLM Orchestration | CrewAI |
| PDF Parsing | pypdf |

## Key Improvements Implemented

- Replaced synchronous inline analysis with queue-based worker processing.
- Added concurrent request handling through Redis + Celery.
- Removed shared global task/agent state by building per-job Crew objects.
- Moved file cleanup to worker lifecycle to avoid request race issues.
- Added explicit async job status API.

## Project Structure

```text
financial-document-analyzer-debug/
|- main.py                  # FastAPI routes
|- celery_app.py            # Celery + Redis config
|- worker_tasks.py          # Background worker task
|- analysis_service.py      # Crew orchestration
|- agents.py                # Agent factory
|- task.py                  # Task factory
|- tools.py                 # PDF text extraction tool
|- requirements.txt
|- .env.example
`- README.md
```

## Environment Variables

Copy template:

```bash
cp .env.example .env
```

Set values:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=openai/gpt-4o-mini
REDIS_URL=redis://localhost:6379/0
```

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI key used by LLM calls |
| `OPENAI_MODEL` | No | Model name (default: `openai/gpt-4o-mini`) |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379/0`) |

## Quick Start

### 1. Create and activate venv

```bash
python -m venv .venv
```

Windows PowerShell:

```bash
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Redis

Docker option:

```bash
docker run --name fda-redis -p 6379:6379 -d redis:7
```

### 4. Start API and worker

Terminal A (API):

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal B (worker, Windows-safe pool):

```bash
python -m celery -A worker_tasks worker --loglevel=info --pool=solo
```

If port 8000 is occupied:

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## API Usage

### Queue a job

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "file=@data/TSLA-Q2-2025-Update.pdf" \
  -F "query=Summarize highlights, risks, and investment signal"
```

Example response:

```json
{
  "status": "queued",
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status_url": "/jobs/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

### Poll status

```bash
curl "http://127.0.0.1:8000/jobs/<job_id>"
```

Job states:
- `queued`
- `processing`
- `completed`
- `failed`

Example completed response:

```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "completed",
  "result": {
    "status": "success",
    "query": "Summarize highlights, risks, and investment signal",
    "analysis": "...",
    "file_processed": "TSLA-Q2-2025-Update.pdf"
  }
}
```

Example failed response:

```json
{
  "job_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "status": "failed",
  "error": "litellm.RateLimitError: ... exceeded your current quota ..."
}
```

## API Reference

### `GET /`
Health endpoint.

### `POST /analyze`
Queue PDF analysis job.

- Content-Type: `multipart/form-data`
- Fields:
  - `file` (required): PDF document
  - `query` (optional): analysis prompt

### `GET /jobs/{job_id}`
Fetch async job state and result.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing OPENAI_API_KEY` | Ensure `.env` exists and restart API/worker |
| `RateLimitError: exceeded quota` | Enable billing / increase limits in OpenAI platform |
| Redis connection refused | Start Redis and verify `REDIS_URL` |
| Port 8000 in use | Run API on `--port 8001` |

Windows notes:
- If `redis-server` is not recognized, run Redis service or use Docker.
- Use `curl.exe` in PowerShell to avoid alias issues.
- Use `python -m uvicorn` and `python -m celery` for reliable interpreter selection.

## Production Notes

- Add authentication/authorization before public exposure.
- Add request size limits and stronger file validation.
- Scale with multiple API instances and worker replicas.
- Add centralized logging and metrics for queue depth, latency, and failures.

## Notes

- `POST /analyze` is intentionally asynchronous.
- Uploaded files are temporary and cleaned by workers after processing.
