"""Read and normalize PDF or manifest-backed plain-text source data."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


@dataclass(frozen=True)
class ProcessingError:
    source: str
    location: str
    error_type: str
    message: str


def load_pdf(
    path: Path, document_id: str, source: str
) -> tuple[list[DocumentPage], list[ProcessingError]]:
    """Extract physical PDF pages and report pages with no usable text.

    OCR is intentionally not implicit. A scanned/empty page is reported so it
    cannot silently count toward corpus coverage.
    """
    pages: list[DocumentPage] = []
    errors: list[ProcessingError] = []
    reader = PdfReader(path)
    for page_number, pdf_page in enumerate(reader.pages, start=1):
        try:
            text = normalize_text(pdf_page.extract_text() or "")
        except Exception as exc:  # pypdf raises provider-specific parse errors
            errors.append(
                ProcessingError(source, str(page_number), "extraction_error", str(exc))
            )
            continue
        if not text:
            errors.append(
                ProcessingError(
                    source,
                    str(page_number),
                    "empty_page",
                    "No extractable text; OCR was not run.",
                )
            )
            continue
        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                unit_id=f"{document_id}-p{page_number:04d}",
                sequence=page_number,
                text=text,
                metadata={"location_type": "physical_page"},
            )
        )
    return pages, errors


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraph boundaries."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        normalized = re.sub(r"[ \t\f\v]+", " ", paragraph)
        normalized = re.sub(r" *\n *", "\n", normalized).strip()
        if normalized:
            paragraphs.append(normalized)
    return "\n\n".join(paragraphs)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_text_manifest(
    manifest_path: Path,
) -> tuple[list[DocumentPage], list[ProcessingError]]:
    """Load every declared non-paginated unit and verify manifest boundaries."""
    manifest_path = manifest_path.resolve()
    root = manifest_path.parent.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source"]
    units_by_path: dict[str, list[dict[str, object]]] = {}
    for unit in manifest["units"]:
        units_by_path.setdefault(unit["source_path"], []).append(unit)

    pages: list[DocumentPage] = []
    errors: list[ProcessingError] = []
    global_sequence = 0
    for file_record in manifest["files"]:
        relative_path = file_record["path"]
        path = root / relative_path
        if not path.is_file():
            errors.append(
                ProcessingError(relative_path, "file", "missing_file", "Declared source is absent")
            )
            continue
        actual_hash = _sha256(path)
        if actual_hash != file_record["sha256"]:
            errors.append(
                ProcessingError(relative_path, "file", "checksum_mismatch", actual_hash)
            )
            continue
        try:
            normalized = normalize_text(path.read_text(encoding="utf-8"))
        except UnicodeError as exc:
            errors.append(
                ProcessingError(relative_path, "file", "decode_error", str(exc))
            )
            continue
        if len(normalized) != file_record["normalized_character_count"]:
            errors.append(
                ProcessingError(
                    relative_path,
                    "file",
                    "normalized_length_mismatch",
                    f"expected {file_record['normalized_character_count']}, got {len(normalized)}",
                )
            )
            continue

        for unit in sorted(units_by_path.get(relative_path, []), key=lambda item: item["sequence_in_chapter"]):
            start = int(unit["normalized_start"])
            end = int(unit["normalized_end"])
            text = normalized[start:end]
            if not text or len(text) != unit["character_count"]:
                errors.append(
                    ProcessingError(
                        relative_path,
                        str(unit["unit_id"]),
                        "unit_boundary_mismatch",
                        f"expected {unit['character_count']} characters, got {len(text)}",
                    )
                )
                continue
            global_sequence += 1
            pages.append(
                DocumentPage(
                    document_id=source["source_id"],
                    source=relative_path,
                    page=None,
                    unit_id=str(unit["unit_id"]),
                    sequence=global_sequence,
                    text=text,
                    metadata={
                        "location_type": "content_unit",
                        "chapter": unit["chapter"],
                        "version": source["version"],
                        "sequence_in_chapter": unit["sequence_in_chapter"],
                        "normalized_start": start,
                        "normalized_end": end,
                    },
                )
            )
    return pages, errors
