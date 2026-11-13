
from __future__ import annotations
import re
from .models import Chunk, DocumentPage


def make_chunk(page: DocumentPage, text: str, index: int, strategy: str) -> Chunk:
    segment = int(page.metadata.get("segment_index", 0))
    return Chunk(
        chunk_id=f"{page.document_id}_p{page.page:04d}_s{segment}_{strategy}_{index:04d}",
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata={**page.metadata, "chunk_strategy": strategy, "chunk_index": index},
    )


def fixed_size(page: DocumentPage, size: int = 500, overlap: int = 50) -> list[Chunk]:
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Require size > 0 and 0 <= overlap < size")
    result = []
    step = size - overlap
    for start in range(0, len(page.text), step):
        piece = page.text[start:start + size]
        if piece.strip():
            result.append(make_chunk(page, piece, len(result), "fixed"))
        if start + size >= len(page.text):
            break
    return result


def by_paragraph(page: DocumentPage, max_size: int = 500) -> list[Chunk]:
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
    result: list[Chunk] = []
    current = ""

    def emit(value: str) -> None:
        if value.strip():
            result.append(make_chunk(page, value.strip(), len(result), "paragraph"))

    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current:
                emit(current)
                current = ""
            # Hard-split overly long paragraphs; documented trade-off for math PDFs.
            for start in range(0, len(paragraph), max_size):
                emit(paragraph[start:start + max_size])
            continue
        candidate = (current + "\n\n" + paragraph) if current else paragraph
        if len(candidate) <= max_size:
            current = candidate
        else:
            emit(current)
            current = paragraph
    if current:
        emit(current)
    return result
