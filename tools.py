import os
from dotenv import load_dotenv
from pypdf import PdfReader
from crewai.tools import BaseTool

load_dotenv()


class FinancialDocumentTool(BaseTool):
    name: str = "read_financial_document"
    description: str = (
        "Read all text from a financial PDF file. "
        "Input should be an absolute or relative path to a PDF file."
    )

    def _run(self, path: str = "data/sample.pdf") -> str:
        if not os.path.exists(path):
            raise FileNotFoundError(f"PDF file not found: {path}")

        reader = PdfReader(path)
        pages_text = []
        for page in reader.pages:
            pages_text.append((page.extract_text() or "").strip())

        return "\n\n".join(text for text in pages_text if text)


read_financial_document = FinancialDocumentTool()
