
"""Load and normalize PDF pages with source traceability."""

import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader
from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode while preserving paragraphs."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    counted_pages: list[int] | None = None,
) -> list[DocumentPage]:

    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    reader = PdfReader(str(path))
    documents = []

    pages = (
        counted_pages
        if counted_pages is not None
        else list(range(1, len(reader.pages) + 1))
    )

    if len(pages) != len(set(pages)):
        raise ValueError("Duplicate page numbers")

    for page_number in pages:
        if not 1 <= page_number <= len(reader.pages):
            raise ValueError(f"Invalid page: {page_number}")

        try:
            raw_text = reader.pages[page_number - 1].extract_text() or ""
        except Exception as exc:
            raise RuntimeError(
                f"PDF extraction failed on page {page_number}"
            ) from exc

        text = normalize_text(raw_text)

        if not text:
            raise ValueError(
                f"No extractable text on page {page_number}"
            )

        documents.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                text=text,
                metadata={
                    "page_id": f"{document_id}_p{page_number:04d}",
                    "physical_page": page_number,
                },
            )
        )

    return documents


def load_from_manifest(
    manifest_path: Path,
    project_dir: Path,
) -> list[DocumentPage]:

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    if not manifest.get("validation", {}).get("meets_minimum"):
        raise ValueError("Corpus manifest is not validated")

    counted_pages = manifest["counted_pages"]

    if len(counted_pages) < 30:
        raise ValueError("Corpus requires at least 30 pages")

    source = manifest["source_path_or_url"]
    pdf_path = project_dir / source

    return load_pdf(
        path=pdf_path,
        document_id=manifest["source_id"],
        source=source,
        counted_pages=counted_pages,
    )
