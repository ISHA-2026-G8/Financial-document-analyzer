from datetime import datetime, timezone
from pathlib import Path

from celery_app import celery_app
from analysis_service import ensure_openai_key, run_crew
from database import SessionLocal
from models import AnalysisJob


def _update_job(job_id: str, **fields) -> None:
    session = SessionLocal()
    try:
        job = session.query(AnalysisJob).filter(AnalysisJob.job_id == job_id).first()
        if not job:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        session.commit()
    finally:
        session.close()


@celery_app.task(name="analyze_financial_document", bind=True)
def analyze_financial_document_task(self, query: str, file_path: str, original_filename: str):
    job_id = self.request.id
    path = Path(file_path)
    _update_job(job_id, status="processing")

    try:
        ensure_openai_key()

        if not path.exists():
            raise FileNotFoundError(f"Uploaded file not found: {file_path}")

        analysis = run_crew(query=query, file_path=file_path)

        payload = {
            "status": "success",
            "query": query,
            "analysis": analysis,
            "file_processed": original_filename,
        }
        _update_job(
            job_id,
            status="completed",
            analysis_text=analysis,
            error_message=None,
            completed_at=datetime.now(timezone.utc),
        )
        return payload
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            error_message=str(exc),
            completed_at=datetime.now(timezone.utc),
        )
        raise
    finally:
        # Worker owns cleanup to avoid deleting files before queued jobs process them.
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
