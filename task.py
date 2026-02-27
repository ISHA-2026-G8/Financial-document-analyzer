from crewai import Task

from tools import read_financial_document


def build_analysis_task(analyst) -> Task:
    return Task(
        description=(
            "Analyze the uploaded financial document at path: {file_path}. "
            "Use the read_financial_document tool to read it first. "
            "Then answer the user query: {query}. "
            "Include: key performance highlights, major risks, and a balanced investment view."
        ),
        expected_output=(
            "A concise financial analysis with these sections: "
            "Summary, Opportunities, Risks, and Recommendation. "
            "Recommendation must include a confidence level (low/medium/high)."
        ),
        agent=analyst,
        tools=[read_financial_document],
        async_execution=False,
    )