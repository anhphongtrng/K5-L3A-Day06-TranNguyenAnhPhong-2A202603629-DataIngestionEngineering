
"""Fixed-size and paragraph-aware chunking."""

import re
from .models import Chunk, DocumentPage


def make_chunk(
    page: DocumentPage,
    text: str,
    index: int,
    strategy: str,
) -> Chunk:
    return Chunk(
        chunk_id=(
            f"{page.document_id}_p{page.page:04d}_"
            f"{strategy}_{index:04d}"
        ),
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        text=text,
        metadata={
            **page.metadata,
            "chunk_strategy": strategy,
            "chunk_index": index,
        },
    )


def fixed_size(
    page: DocumentPage,
    size: int,
    overlap: int,
) -> list[Chunk]:

    if size <= 0 or not 0 <= overlap < size:
        raise ValueError("Invalid size or overlap")

    text = page.text
    chunks = []
    step = size - overlap

    for index, start in enumerate(range(0, len(text), step)):
        content = text[start:start + size]

        if not content.strip():
            continue

        chunks.append(
            make_chunk(page, content, index, "fixed")
        )

        if start + size >= len(text):
            break

    return chunks


def by_paragraph(
    page: DocumentPage,
    max_size: int,
) -> list[Chunk]:

    if max_size <= 0:
        raise ValueError("max_size must be positive")

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", page.text)
        if p.strip()
    ]

    chunks = []
    current = ""

    def append_chunk(content: str) -> None:
        if content.strip():
            chunks.append(
                make_chunk(
                    page,
                    content.strip(),
                    len(chunks),
                    "paragraph",
                )
            )

    for paragraph in paragraphs:
        # Oversized paragraphs need splitting
        if len(paragraph) > max_size:
            if current:
                append_chunk(current)
                current = ""

            for start in range(0, len(paragraph), max_size):
                append_chunk(paragraph[start:start + max_size])
            continue

        candidate = (
            f"{current}\n\n{paragraph}"
            if current else paragraph
        )

        if len(candidate) <= max_size:
            current = candidate
        else:
            append_chunk(current)
            current = paragraph

    if current:
        append_chunk(current)

    return chunks
