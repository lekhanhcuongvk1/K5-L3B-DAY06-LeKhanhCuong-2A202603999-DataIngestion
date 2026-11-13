"""Validate CP4 trace coverage, metrics, freeze integrity, and manual audits."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter"
if str(STARTER) not in sys.path:
    sys.path.insert(0, str(STARTER))

from src.evaluation import summarize  # noqa: E402


RESULTS = ROOT / "results"
TRACES = RESULTS / "traces"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> None:
    benchmark = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    questions_by_split = {
        split: {q["id"] for q in benchmark["questions"] if q["split"] == split}
        for split in ("dev", "test")
    }
    all_traces = []
    for split, expected_count in (("dev", 15), ("test", 5)):
        for strategy in ("A", "B", "C"):
            rows = read_jsonl(TRACES / f"{split}_{strategy}.jsonl")
            if len(rows) != expected_count:
                fail(f"{split}/{strategy} has {len(rows)} traces, expected {expected_count}")
            if {row["question_id"] for row in rows} != questions_by_split[split]:
                fail(f"{split}/{strategy} question coverage mismatch")
            if any(row["strategy"] != strategy or row["split"] != split for row in rows):
                fail(f"{split}/{strategy} trace labels mismatch")
            if any(len(row["retrieved_top3"]) != 3 for row in rows):
                fail(f"{split}/{strategy} contains a non-top-3 trace")
            all_traces.extend(rows)
    if len(all_traces) != 60:
        fail("Expected 60 question-strategy traces")

    calculated = summarize(all_traces)["metrics"]
    with (RESULTS / "retrieval_metrics.csv").open(encoding="utf-8", newline="") as source:
        stored = list(csv.DictReader(source))
    for row, expected in zip(stored, calculated, strict=True):
        for key in ("strategy", "split"):
            if row[key] != str(expected[key]):
                fail(f"Metric identity mismatch for {key}")
        for key in (
            "questions", "hit_at_1_n", "hit_at_1_N",
            "evidence_hit_at_3_n", "evidence_hit_at_3_N",
        ):
            if int(row[key]) != expected[key]:
                fail(f"Metric mismatch for {row['strategy']}/{row['split']}/{key}")

    freeze = json.loads((RESULTS / "strategy_freeze.json").read_text(encoding="utf-8"))
    marker = json.loads((RESULTS / ".test_completed").read_text(encoding="utf-8"))
    if freeze["selected_strategy"] != "B":
        fail("Frozen selected strategy is not B")
    if datetime.fromisoformat(freeze["frozen_at"]) >= datetime.fromisoformat(marker["completed_at"]):
        fail("Strategy freeze does not precede Test completion")
    if freeze["questions_sha256"] != sha256(ROOT / "benchmark" / "questions.json"):
        fail("Questions changed after freeze")
    for filename, expected in freeze["code_files_sha256"].items():
        path = STARTER / "scripts" / filename if filename == "run_benchmark.py" else STARTER / "src" / filename
        if sha256(path) != expected:
            fail(f"Frozen code changed: {filename}")

    trace_index = {(row["split"], row["question_id"], row["strategy"]): row for row in all_traces}
    for split in ("dev", "test"):
        for question_id in questions_by_split[split]:
            row_b = trace_index[(split, question_id, "B")]
            row_c = trace_index[(split, question_id, "C")]
            if row_c["filters_applied"] is None:
                ids_b = [hit["chunk_id"] for hit in row_b["retrieved_top3"]]
                ids_c = [hit["chunk_id"] for hit in row_c["retrieved_top3"]]
                if ids_b != ids_c:
                    fail(f"B/C differ without a filter for {question_id}")
            elif any(
                hit["metadata"].get("chapter") != row_c["filters_applied"]["chapter"]
                for hit in row_c["retrieved_top3"]
            ):
                fail(f"C filter violation for {question_id}")

    with (RESULTS / "coherence_audit.csv").open(encoding="utf-8", newline="") as source:
        coherence = list(csv.DictReader(source))
    if len(coherence) != 30 or Counter(row["strategy"] for row in coherence) != Counter(A=10, B=10, C=10):
        fail("Coherence audit coverage mismatch")
    if any(not row["rationale"] or row["score_0_2"] not in {"0", "1", "2"} for row in coherence):
        fail("Invalid coherence label/rationale")

    with (RESULTS / "metadata_audit.csv").open(encoding="utf-8", newline="") as source:
        metadata = list(csv.DictReader(source))
    if len(metadata) != 45 or any(
        row["metadata_complete"] != "true" or row["metadata_correct"] != "true"
        for row in metadata
    ):
        fail("Metadata audit is incomplete or contains incorrect records")
    filtered = [row for row in metadata if row["filter_compliant"] != "N/A"]
    if len(filtered) != 6 or any(row["filter_compliant"] != "true" for row in filtered):
        fail("Filter compliance audit mismatch")

    with (RESULTS / "grounding_audit.csv").open(encoding="utf-8", newline="") as source:
        grounding = list(csv.DictReader(source))
    if len(grounding) != 15 or Counter(row["strategy"] for row in grounding) != Counter(A=5, B=5, C=5):
        fail("Grounding audit coverage mismatch")
    if any(not row["rationale"] or row["score_0_2"] not in {"0", "1", "2"} for row in grounding):
        fail("Invalid grounding label/rationale")

    print(
        "CP4 validation OK: 60 traces/180 hits, 6 metric rows, freeze before Test, "
        "30 coherence labels, 45 metadata records, 15 grounding labels."
    )


if __name__ == "__main__":
    main()
