"""Validate CP2 chunk artifacts against the frozen corpus manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter"
if str(STARTER) not in sys.path:
    sys.path.insert(0, str(STARTER))

from src.ingestion import load_text_manifest  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def fail(message: str) -> None:
    raise SystemExit(f"CP2 validation failed: {message}")


def main() -> None:
    manifest_path = ROOT / "data" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filter_field = manifest["filter_metadata"]["field"]
    units, errors = load_text_manifest(manifest_path)
    if errors:
        fail(f"loader returned {len(errors)} processing errors")
    unit_map = {unit.unit_id: unit for unit in units}
    if len(unit_map) != manifest["summary"]["content_unit_count"]:
        fail("unit count differs from manifest")

    results = ROOT / "results"
    errors_path = results / "processing_errors.jsonl"
    if not errors_path.is_file() or errors_path.read_text(encoding="utf-8").strip():
        fail("processing_errors.jsonl must exist and be empty")

    counts: dict[str, int] = {}
    for strategy in ("A", "B"):
        records = read_jsonl(results / f"chunks_{strategy}.jsonl")
        counts[strategy] = len(records)
        if not records:
            fail(f"strategy {strategy} has no chunks")
        ids = [str(record["chunk_id"]) for record in records]
        if len(ids) != len(set(ids)):
            fail(f"strategy {strategy} contains duplicate chunk IDs")
        by_unit: dict[str, list[dict[str, object]]] = {}
        for record in records:
            unit_id = str(record["unit_id"])
            unit = unit_map.get(unit_id)
            if unit is None:
                fail(f"{strategy} references unknown unit {unit_id}")
            start, end = int(record["char_start"]), int(record["char_end"])
            if start < 0 or end <= start or end > len(unit.text):
                fail(f"{record['chunk_id']} has an invalid source span")
            if record["text"] != unit.text[start:end]:
                fail(f"{record['chunk_id']} text differs from its source span")
            if record["document_id"] != unit.document_id or record["source"] != unit.source:
                fail(f"{record['chunk_id']} provenance differs from its unit")
            metadata = record["metadata"]
            for field in (filter_field, "version", "title", "canonical_url"):
                if not metadata.get(field) or metadata.get(field) != unit.metadata.get(field):
                    fail(f"{record['chunk_id']} has incorrect metadata field {field}")
            if metadata.get("strategy") != strategy:
                fail(f"{record['chunk_id']} has incorrect strategy metadata")
            by_unit.setdefault(unit_id, []).append(record)
        if set(by_unit) != set(unit_map):
            fail(f"strategy {strategy} does not cover all units")
        for unit_id, unit_records in by_unit.items():
            unit = unit_map[unit_id]
            ordered = sorted(unit_records, key=lambda row: int(row["char_start"]))
            covered = {
                index
                for record in ordered
                for index in range(int(record["char_start"]), int(record["char_end"]))
            }
            if covered != set(range(len(unit.text))):
                fail(f"strategy {strategy} leaves a gap in {unit_id}")
            if strategy == "A":
                if any(len(str(record["text"])) > 500 for record in ordered):
                    fail(f"strategy A exceeds 500 characters in {unit_id}")
            else:
                if any(len(str(record["text"])) > 1_000 for record in ordered):
                    fail(f"strategy B exceeds 1,000 characters in {unit_id}")
                if "".join(str(record["text"]) for record in ordered) != unit.text:
                    fail(f"strategy B does not reconstruct {unit_id} exactly")

    stats = json.loads((results / "chunk_stats.json").read_text(encoding="utf-8"))
    if stats["corpus"]["processing_error_count"] != 0:
        fail("chunk_stats reports processing errors")
    if stats["corpus"]["document_count"] != len(units):
        fail("chunk_stats document count is incorrect")
    if stats["strategy_A"]["chunk_count"] != counts["A"]:
        fail("strategy A count differs from chunk_stats")
    if stats["strategy_B"]["chunk_count"] != counts["B"]:
        fail("strategy B count differs from chunk_stats")
    print(
        f"CP2 validation OK: {len(units)} units/documents, {counts['A']} A chunks, "
        f"{counts['B']} B chunks, complete spans, stable unique IDs, metadata and 0 errors."
    )


if __name__ == "__main__":
    main()
