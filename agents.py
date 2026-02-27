import os
from dotenv import load_dotenv
from crewai import Agent, LLM

from tools import read_financial_document

load_dotenv()


def _build_llm() -> LLM:
    model = os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")
    return LLM(model=model, temperature=0.1)


def create_financial_analyst() -> Agent:
    return Agent(
        role="Senior Financial Analyst",
        goal=(
            "Analyze uploaded financial documents and provide grounded, clear investment "
            "insights for this query: {query}"
        ),
        verbose=True,
        memory=False,
        backstory=(
            "You are a careful financial analyst. You only use information available in "
            "the provided document and clearly call out uncertainty."
        ),
        tools=[read_financial_document],
        llm=_build_llm(),
        max_iter=3,
        allow_delegation=False,
    )