"""Shared data contracts with traceability from chunks to source units."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentPage:
    document_id: str
    source: str
    page: int | None
    unit_id: str
    sequence: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source: str
    page: int | None
    unit_id: str
    sequence: int
    char_start: int
    char_end: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
