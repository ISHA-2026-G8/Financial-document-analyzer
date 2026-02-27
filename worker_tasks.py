from pathlib import Path

from celery_app import celery_app
from analysis_service import ensure_openai_key, run_crew


@celery_app.task(name="analyze_financial_document")
def analyze_financial_document_task(query: str, file_path: str, original_filename: str):
    path = Path(file_path)
    try:
        ensure_openai_key()

        if not path.exists():
            raise FileNotFoundError(f"Uploaded file not found: {file_path}")

        analysis = run_crew(query=query, file_path=file_path)

        return {
            "status": "success",
            "query": query,
            "analysis": analysis,
            "file_processed": original_filename,
        }
    finally:
        # Worker owns cleanup to avoid deleting files before queued jobs process them.
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
