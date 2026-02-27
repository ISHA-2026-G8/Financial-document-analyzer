import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from celery.result import AsyncResult
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from celery_app import celery_app
from database import get_session, init_db
from models import AnalysisJob, User

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


def _get_or_create_user(session: Session, name: str | None, email: str | None) -> User | None:
    normalized_email = (email or "").strip().lower() or None
    normalized_name = (name or "").strip() or None

    if not normalized_email and not normalized_name:
        return None

    if normalized_email:
        user = session.query(User).filter(User.email == normalized_email).first()
        if user:
            if normalized_name and not user.name:
                user.name = normalized_name
                session.commit()
            return user

    user = User(name=normalized_name, email=normalized_email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@app.on_event("startup")
async def startup_event():
    init_db()


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
    user_name: str | None = Form(default=None),
    user_email: str | None = Form(default=None),
    session: Session = Depends(get_session),
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
    resolved_query = _resolve_query(query)

    try:
        with file_path.open("wb") as out_file:
            shutil.copyfileobj(file.file, out_file)

        if file_path.stat().st_size == 0:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

        if user_email and "@" not in user_email:
            raise HTTPException(status_code=400, detail="Invalid user_email format")

        user = _get_or_create_user(session, user_name, user_email)
        db_job = AnalysisJob(
            job_id=job_id,
            user_id=user.id if user else None,
            query=resolved_query,
            file_name=file.filename,
            file_path=str(file_path),
            status="queued",
        )
        session.add(db_job)
        session.commit()

        celery_app.send_task(
            "analyze_financial_document",
            kwargs={
                "query": resolved_query,
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
        db_job = session.query(AnalysisJob).filter(AnalysisJob.job_id == job_id).first()
        if db_job:
            db_job.status = "failed"
            db_job.error_message = f"Queue error: {exc}"
            db_job.completed_at = datetime.now(timezone.utc)
            session.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Error queuing analysis job: {exc}",
        )


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str, session: Session = Depends(get_session)):
    db_job = session.query(AnalysisJob).filter(AnalysisJob.job_id == job_id).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = AsyncResult(job_id, app=celery_app)
    state = result.state

    if state in {"STARTED", "RETRY"} and db_job.status == "queued":
        db_job.status = "processing"
        session.commit()

    if db_job.status in {"queued", "processing"}:
        return {"job_id": job_id, "status": db_job.status}

    if db_job.status == "completed":
        return {
            "job_id": job_id,
            "status": "completed",
            "result": {
                "status": "success",
                "query": db_job.query,
                "analysis": db_job.analysis_text,
                "file_processed": db_job.file_name,
                "user_id": db_job.user_id,
            },
        }

    if db_job.status == "failed":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": db_job.error_message or str(result.result),
            "user_id": db_job.user_id,
        }

    return {"job_id": job_id, "status": db_job.status}


@app.get("/users/{user_id}/jobs")
async def get_user_jobs(user_id: int, session: Session = Depends(get_session)):
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    jobs = (
        session.query(AnalysisJob)
        .filter(AnalysisJob.user_id == user_id)
        .order_by(AnalysisJob.created_at.desc())
        .all()
    )
    return {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "jobs": [
            {
                "job_id": job.job_id,
                "status": job.status,
                "query": job.query,
                "file_name": job.file_name,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
            for job in jobs
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
