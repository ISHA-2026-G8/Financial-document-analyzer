import os
import re
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from celery.result import AsyncResult
from dotenv import load_dotenv

from celery_app import celery_app

load_dotenv()

app = FastAPI(title="Financial Document Analyzer")

DATA_DIR = Path("data/uploads")
DEFAULT_QUERY = "Analyze this financial document for investment insights"


def _sanitize_filename(filename: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return safe_name[:120] or "uploaded.pdf"


def _resolve_query(query: str | None) -> str:
    resolved = (query or DEFAULT_QUERY).strip()
    return resolved or DEFAULT_QUERY


@app.get("/")
async def root():
    return {
        "message": "Financial Document Analyzer API is running",
        "docs": "/docs",
    }


@app.post("/analyze", status_code=202)
async def analyze_document(
    file: UploadFile = File(...),
    query: str = Form(default=DEFAULT_QUERY),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Missing OPENAI_API_KEY environment variable",
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())
    safe_filename = _sanitize_filename(file.filename)
    file_path = DATA_DIR / f"{job_id}_{safe_filename}"

    try:
        with file_path.open("wb") as out_file:
            shutil.copyfileobj(file.file, out_file)

        if file_path.stat().st_size == 0:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

        celery_app.send_task(
            "analyze_financial_document",
            kwargs={
                "query": _resolve_query(query),
                "file_path": str(file_path),
                "original_filename": file.filename,
            },
            task_id=job_id,
        )

        return {
            "status": "queued",
            "job_id": job_id,
            "status_url": f"/jobs/{job_id}",
        }

    except HTTPException:
        raise
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error queuing analysis job: {exc}",
        )


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    result = AsyncResult(job_id, app=celery_app)
    state = result.state

    if state == "PENDING":
        return {"job_id": job_id, "status": "queued"}

    if state in {"STARTED", "RETRY"}:
        return {"job_id": job_id, "status": "processing"}

    if state == "SUCCESS":
        payload = result.result if isinstance(result.result, dict) else {"analysis": str(result.result)}
        return {
            "job_id": job_id,
            "status": "completed",
            "result": payload,
        }

    if state == "FAILURE":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(result.result),
        }

    return {"job_id": job_id, "status": state.lower()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
