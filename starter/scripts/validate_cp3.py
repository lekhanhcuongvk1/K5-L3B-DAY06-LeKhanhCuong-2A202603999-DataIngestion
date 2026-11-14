"""Validate CP3 model selection, persistent index, filters and Dev-only smoke traces."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter"
if str(STARTER) not in sys.path:
    sys.path.insert(0, str(STARTER))

from src.store import PgVectorStore  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"CP3 validation failed: {message}")


def main() -> None:
    load_dotenv(STARTER / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        fail("DATABASE_URL is missing")
    questions_path = ROOT / "benchmark" / "questions.json"
    split = json.loads((ROOT / "benchmark" / "split_manifest.json").read_text(encoding="utf-8"))
    if sha256(questions_path) != split["questions_sha256"]:
        fail("frozen questions checksum mismatch")

    selection = json.loads((ROOT / "results" / "model_selection.json").read_text(encoding="utf-8"))
    bakeoff = json.loads((ROOT / "results" / "model_bakeoff_dev.json").read_text(encoding="utf-8"))
    if selection != bakeoff["summary"]:
        fail("model selection summary differs from bake-off artifact")
    if selection["test_retrieval_run"] is not False:
        fail("model selection does not certify unopened Test")
    if any(trace["split"] != "dev" for trace in bakeoff["traces"]):
        fail("model bake-off contains a non-Dev trace")
    counts = Counter(trace["candidate"] for trace in bakeoff["traces"])
    if counts != {"multilingual_minilm": 15, "vietnamese_bkai": 15}:
        fail(f"unexpected bake-off trace counts: {dict(counts)}")
    for candidate in selection["candidates"]:
        traces = [row for row in bakeoff["traces"] if row["candidate"] == candidate["candidate"]]
        if sum(bool(row["hit_at_1"]) for row in traces) != candidate["hit_at_1_n"]:
            fail(f"Hit@1 mismatch for {candidate['candidate']}")
        if sum(bool(row["evidence_hit_at_3"]) for row in traces) != candidate["evidence_hit_at_3_n"]:
            fail(f"Hit@3 mismatch for {candidate['candidate']}")
    ranked = sorted(
        selection["candidates"],
        key=lambda row: (
            row["evidence_hit_at_3_n"], row["hit_at_1_n"],
            -row["mean_query_embedding_ms"], -row["mean_retrieval_ms"],
        ),
        reverse=True,
    )
    if selection["selected_candidate"] != ranked[0]["candidate"]:
        fail("selected model does not follow the frozen ranking rule")

    metadata = json.loads((ROOT / "results" / "run_metadata.json").read_text(encoding="utf-8"))
    if metadata["model"]["name"] != selection["selected_model"]:
        fail("official index model differs from Dev selection")
    if metadata["model"]["dimensions"] != 768 or metadata["model"]["revision"] != (
        "84f9d9ada0d1a3c37557398b9ae9fcedcdf40be0"
    ):
        fail("official model dimension/revision is incorrect")
    if metadata["benchmark_integrity"]["test_retrieval_run"] is not False:
        fail("run metadata does not certify unopened Test")

    table = metadata["store"]["table"]
    store = PgVectorStore(database_url, 768, table_name=table)
    store.create_schema()
    expected = {"A": 759, "B": 418}
    actual = {strategy: store.count(strategy) for strategy in expected}
    if actual != expected or metadata["counts"]["after_second_upsert"] != expected:
        fail(f"persistent counts differ: {actual}")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "WHERE a.attrelid = %s::regclass AND a.attname = 'embedding'", (table,)
            )
            if cursor.fetchone()[0] != "vector(768)":
                fail("official table is not vector(768)")
            cursor.execute(
                f'SELECT strategy, count(DISTINCT document_id), '
                f"count(*) FILTER (WHERE metadata->>'collection' IS NULL), count(*) "
                f'FROM "{table}" GROUP BY strategy ORDER BY strategy'
            )
            rows = cursor.fetchall()
            if rows != [("A", 30, 0, 759), ("B", 30, 0, 418)]:
                fail(f"database provenance/count audit differs: {rows}")

    smoke = json.loads((ROOT / "results" / "smoke_retrieval.json").read_text(encoding="utf-8"))
    if len(smoke) != 9 or any(row["split"] != "dev" for row in smoke):
        fail("smoke artifact must contain 9 Dev-only traces")
    if {row["question_id"] for row in smoke} != {"Q01", "Q04", "Q10"}:
        fail("unexpected smoke question IDs")
    if any(len(row["top3"]) != 3 for row in smoke):
        fail("a smoke trace does not contain top-3")
    for question_id in ("Q04", "Q10"):
        trace = next(
            row for row in smoke if row["question_id"] == question_id and row["strategy"] == "C"
        )
        filters = trace["filters_applied"]
        if not filters or any(
            any(hit["metadata"].get(key) != value for key, value in filters.items())
            for hit in trace["top3"]
        ):
            fail(f"C/{question_id} violates its collection filter")
    trace_b = next(row for row in smoke if row["question_id"] == "Q01" and row["strategy"] == "B")
    trace_c = next(row for row in smoke if row["question_id"] == "Q01" and row["strategy"] == "C")
    if [hit["chunk_id"] for hit in trace_b["top3"]] != [
        hit["chunk_id"] for hit in trace_c["top3"]
    ]:
        fail("B/C differ on the unfiltered deterministic smoke query")
    test_marker = ROOT / "results" / ".test_completed"
    test_traces = list((ROOT / "results").glob("traces/test_*.jsonl"))
    freeze = ROOT / "results" / "strategy_freeze.json"
    if (test_marker.exists() or test_traces) and not (test_marker.exists() and freeze.exists()):
        fail("Test artifacts exist without both the CP4 freeze and one-time marker")

    print(
        "CP3 validation OK: BKAI selected 14/15 vs MiniLM 12/15 Dev Hit@3; "
        "vector(768), A=759/B=418 persistent rows, 9 Dev smoke traces, filters and "
        "idempotence PASS; CP3 metadata certifies Test was unopened at indexing time."
    )


if __name__ == "__main__":
    main()
