from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader
from .models import DocumentPage


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
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
    numbers = counted_pages if counted_pages is not None else list(range(1, len(reader.pages) + 1))
    if len(numbers) != len(set(numbers)):
        raise ValueError("Duplicate physical page numbers in manifest")
    result: list[DocumentPage] = []
    for number in numbers:
        if not 1 <= number <= len(reader.pages):
            raise ValueError(f"Out-of-range PDF page: {number}")
        try:
            text = normalize_text(reader.pages[number - 1].extract_text() or "")
        except Exception as exc:
            raise RuntimeError(f"Cannot extract PDF page {number}") from exc
        if not text:
            raise ValueError(f"Selected PDF page {number} has no extractable text")
        result.append(DocumentPage(
            document_id=document_id,
            source=source,
            page=number,
            text=text,
            metadata={
                "page_id": f"{document_id}_p{number:04d}",
                "physical_page": number,
                "segment_index": 0,
            },
        ))
    return result


def load_from_manifest(manifest_path: Path, project_dir: Path) -> list[DocumentPage]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("validation", {}).get("meets_minimum", False):
        raise ValueError("Manifest is not validated; review the corpus before ingestion")
    counted = manifest.get("counted_pages", [])
    if len(counted) < 30:
        raise ValueError("At least 30 counted physical PDF pages are required")
    source = manifest["source_path_or_url"]
    if source.startswith(("https://", "http://")):
        raise ValueError("This local PDF pipeline requires source_path_or_url to be a local file")
    path = (project_dir / source).resolve()
    if not path.is_relative_to(project_dir.resolve()):
        raise ValueError("Manifest source path must stay inside the repository")
    return load_pdf(path, manifest["source_id"], source, counted)


def attach_sections(
    pages: list[DocumentPage],
    section_map_path: Path | None = None,
) -> list[DocumentPage]:
    """Split mixed pages at actual headings; each output segment has one scalar section."""
    if section_map_path is None:
        section_map_path = Path(__file__).resolve().parents[2] / "data" / "section_map.json"
    mapping = json.loads(section_map_path.read_text(encoding="utf-8"))
    sections = mapping["page_sections"]
    mixed = mapping.get("mixed_section_pages", {})
    titles = mapping.get("section_titles", {})
    result: list[DocumentPage] = []

    for page in pages:
        page_key = str(page.page)
        if page_key not in sections:
            raise ValueError(f"Missing section mapping for physical page {page.page}")
        value = sections[page_key]
        if isinstance(value, str):
            result.append(DocumentPage(
                document_id=page.document_id, source=page.source, page=page.page,
                text=page.text,
                metadata={**page.metadata, "section": value,
                          "section_title": titles.get(value, ""), "segment_index": 0},
            ))
            continue
        if not isinstance(value, list) or len(value) != 2 or not all(isinstance(s, str) for s in value):
            raise ValueError(f"Invalid mixed-section mapping on page {page.page}: {value}")
        info = mixed.get(page_key)
        if not info or info.get("before_heading") != value[0] or info.get("after_heading") != value[1]:
            raise ValueError(f"Mixed page {page.page} needs verified before/after heading data")
        heading = info["heading"]
        # Allow whitespace/newlines in extracted heading (not arbitrary fuzzy matching).
        heading_regex = r"\s+".join(re.escape(token) for token in heading.split())
        match = re.search(heading_regex, page.text, flags=re.IGNORECASE)
        if match is None:
            raise ValueError(
                f"Could not find section transition heading on page {page.page}: {heading!r}. "
                "Inspect the extracted page text and original PDF instead of guessing a section."
            )
        for segment_index, (segment_text, section_id) in enumerate((
            (page.text[:match.start()].strip(), value[0]),
            (page.text[match.start():].strip(), value[1]),
        )):
            if not segment_text:
                raise ValueError(f"Empty section segment on page {page.page}; verify heading boundary")
            result.append(DocumentPage(
                document_id=page.document_id, source=page.source, page=page.page,
                text=segment_text,
                metadata={**page.metadata, "section": section_id,
                          "section_title": titles.get(section_id, ""),
                          "segment_index": segment_index},
            ))
    return result
