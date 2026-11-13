"""Generate CP2 A/B chunks, processing errors, and measured statistics."""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter"
if str(STARTER) not in sys.path:
    sys.path.insert(0, str(STARTER))

from src.chunking import by_paragraph, fixed_size  # noqa: E402
from src.ingestion import load_text_manifest  # noqa: E402


MANIFEST_PATH = ROOT / "data" / "manifest.json"
RESULTS_DIR = ROOT / "results"
FIXED_SIZE = 500
FIXED_OVERLAP = 50
PARAGRAPH_MAX_SIZE = 1_000


def percentile_95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


def chunk_statistics(chunks: list[object]) -> dict[str, object]:
    lengths = [len(chunk.text) for chunk in chunks]
    return {
        "chunk_count": len(chunks),
        "chunk_character_count_including_overlap": sum(lengths),
        "minimum_chunk_characters": min(lengths),
        "maximum_chunk_characters": max(lengths),
        "mean_chunk_characters": round(statistics.mean(lengths), 2),
        "median_chunk_characters": statistics.median(lengths),
        "p95_chunk_characters": percentile_95(lengths),
    }


def write_jsonl(path: Path, records: list[object]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            payload = asdict(record) if not isinstance(record, dict) else record
            output.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    units, errors = load_text_manifest(MANIFEST_PATH)
    if errors:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        write_jsonl(RESULTS_DIR / "processing_errors.jsonl", errors)
        raise SystemExit(f"Corpus processing failed with {len(errors)} error(s)")
    if len(units) < 30:
        raise SystemExit(f"Only {len(units)} valid units; at least 30 are required")

    chunks_a = [chunk for unit in units for chunk in fixed_size(unit, FIXED_SIZE, FIXED_OVERLAP)]
    chunks_b = [chunk for unit in units for chunk in by_paragraph(unit, PARAGRAPH_MAX_SIZE)]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(RESULTS_DIR / "chunks_A.jsonl", chunks_a)
    write_jsonl(RESULTS_DIR / "chunks_B.jsonl", chunks_b)
    write_jsonl(RESULTS_DIR / "processing_errors.jsonl", errors)

    source_characters = sum(len(unit.text) for unit in units)
    stats = {
        "corpus": {
            "document_id": units[0].document_id,
            "valid_unit_count": len(units),
            "processing_error_count": len(errors),
            "normalized_source_characters": source_characters,
            "location_type": "content_unit",
            "page": None,
        },
        "strategy_A": {
            "chunking": "fixed_size",
            "size": FIXED_SIZE,
            "overlap": FIXED_OVERLAP,
            **chunk_statistics(chunks_a),
        },
        "strategy_B": {
            "chunking": "paragraph_aware",
            "max_size": PARAGRAPH_MAX_SIZE,
            "overlap": 0,
            **chunk_statistics(chunks_b),
        },
        "metadata_fields": [
            "document_id", "source", "page", "unit_id", "chapter", "version",
            "sequence_in_chapter", "char_start", "char_end",
        ],
        "coverage_check": {
            "strategy_A_all_units_present": len({chunk.unit_id for chunk in chunks_a}) == len(units),
            "strategy_B_all_units_present": len({chunk.unit_id for chunk in chunks_b}) == len(units),
        },
    }
    (RESULTS_DIR / "chunk_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"CP2 processing OK: {len(units)} units, {source_characters} source characters, "
        f"0 errors, {len(chunks_a)} A chunks, {len(chunks_b)} B chunks."
    )


if __name__ == "__main__":
    main()
