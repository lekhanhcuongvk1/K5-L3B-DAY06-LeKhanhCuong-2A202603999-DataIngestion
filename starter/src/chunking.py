"""Fixed-size and paragraph-aware chunking with stable source spans."""
from __future__ import annotations

import hashlib

from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, strategy: str, ordinal: int, start: int, end: int) -> Chunk:
    text = page.text[start:end]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    chunk_id = f"{strategy}:{page.unit_id}:{ordinal:04d}:{digest}"
    metadata = dict(page.metadata)
    metadata.update({"strategy": strategy, "chunk_ordinal": ordinal})
    return Chunk(
        chunk_id=chunk_id,
        document_id=page.document_id,
        source=page.source,
        page=page.page,
        unit_id=page.unit_id,
        sequence=page.sequence,
        char_start=start,
        char_end=end,
        text=text,
        metadata=metadata,
    )


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split into overlapping character windows without losing source coverage."""
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must satisfy 0 <= overlap < size")
    if not page.text:
        return []
    chunks: list[Chunk] = []
    step = size - overlap
    for ordinal, start in enumerate(range(0, len(page.text), step), start=1):
        end = min(start + size, len(page.text))
        chunks.append(_chunk(page, "A", ordinal, start, end))
        if end == len(page.text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Prefer paragraph boundaries and hard-split oversized paragraphs."""
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    if not page.text:
        return []
    chunks: list[Chunk] = []
    start = 0
    ordinal = 1
    text_length = len(page.text)
    while start < text_length:
        hard_end = min(start + max_size, text_length)
        end = hard_end
        if hard_end < text_length:
            # The separator is included in this chunk, so its start must be at
            # most hard_end - 2 to keep the declared max_size strict.
            boundary = page.text.rfind("\n\n", start + 1, hard_end)
            if boundary > start:
                end = boundary + 2
        if end <= start:
            end = hard_end
        chunks.append(_chunk(page, "B", ordinal, start, end))
        start = end
        ordinal += 1
    return chunks
