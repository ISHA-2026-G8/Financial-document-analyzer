import os

from crewai import Crew, Process

from agents import create_financial_analyst
from task import build_analysis_task


def run_crew(query: str, file_path: str) -> str:
    """Run CrewAI analysis for a given document path and user query."""
    analyst = create_financial_analyst()
    analysis_task = build_analysis_task(analyst)

    financial_crew = Crew(
        agents=[analyst],
        tasks=[analysis_task],
        process=Process.sequential,
    )

    result = financial_crew.kickoff(inputs={"query": query, "file_path": file_path})
    return str(result)


def ensure_openai_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable")