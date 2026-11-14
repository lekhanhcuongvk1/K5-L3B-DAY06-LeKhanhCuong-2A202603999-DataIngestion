"""Validate CP4 traces, metrics, freeze integrity and all manual audits."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
TRACES = RESULTS / "traces"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def fail(message: str) -> None:
    raise SystemExit(f"CP4 validation failed: {message}")


def main() -> None:
    benchmark = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    questions = {row["id"]: row for row in benchmark["questions"]}
    all_traces = []
    for split, expected_n in (("dev", 15), ("test", 5)):
        expected_ids = {row["id"] for row in benchmark["questions"] if row["split"] == split}
        for strategy in ("A", "B", "C"):
            rows = read_jsonl(TRACES / f"{split}_{strategy}.jsonl")
            if len(rows) != expected_n or {row["question_id"] for row in rows} != expected_ids:
                fail(f"{split}/{strategy} trace coverage differs from benchmark")
            if any(len(row["retrieved_top3"]) != 3 for row in rows):
                fail(f"{split}/{strategy} does not have exactly top-3 for every question")
            if any(row["strategy"] != strategy or row["split"] != split for row in rows):
                fail(f"{split}/{strategy} trace identity mismatch")
            all_traces.extend(rows)

    if len(all_traces) != 60:
        fail("expected 60 question-strategy traces")
    for split in ("dev", "test"):
        traces_by_key = {(row["question_id"], row["strategy"]): row for row in all_traces if row["split"] == split}
        for question_id in {row["id"] for row in benchmark["questions"] if row["split"] == split}:
            question = questions[question_id]
            row_b = traces_by_key[(question_id, "B")]
            row_c = traces_by_key[(question_id, "C")]
            if question["filter"] is None:
                if [hit["chunk_id"] for hit in row_b["retrieved_top3"]] != [
                    hit["chunk_id"] for hit in row_c["retrieved_top3"]
                ]:
                    fail(f"B/C differ for unfiltered {question_id}")
            else:
                if row_c["filters_applied"] != question["filter"]:
                    fail(f"C did not apply declared filter for {question_id}")
                if any(
                    any(hit["metadata"].get(key) != value for key, value in question["filter"].items())
                    for hit in row_c["retrieved_top3"]
                ):
                    fail(f"C filter compliance failed for {question_id}")

    metrics = read_csv(RESULTS / "retrieval_metrics.csv")
    if len(metrics) != 6:
        fail("retrieval_metrics.csv must contain 6 strategy/split rows")
    for row in metrics:
        group = [
            trace for trace in all_traces
            if trace["strategy"] == row["strategy"] and trace["split"] == row["split"]
        ]
        if int(row["hit_at_1_n"]) != sum(bool(trace["hit_at_1"]) for trace in group):
            fail(f"Hit@1 numerator mismatch for {row['strategy']}/{row['split']}")
        if int(row["evidence_hit_at_3_n"]) != sum(
            bool(trace["evidence_hit_at_3"]) for trace in group
        ):
            fail(f"Hit@3 numerator mismatch for {row['strategy']}/{row['split']}")
        if int(row["hit_at_1_N"]) != len(group) or int(row["evidence_hit_at_3_N"]) != len(group):
            fail(f"metric denominator mismatch for {row['strategy']}/{row['split']}")

    freeze = json.loads((RESULTS / "strategy_freeze.json").read_text(encoding="utf-8"))
    marker = json.loads((RESULTS / ".test_completed").read_text(encoding="utf-8"))
    if freeze["selected_strategy"] != "B" or marker["selected_strategy_before_test"] != "B":
        fail("strategy B was not frozen before Test")
    if datetime.fromisoformat(freeze["frozen_at"]) >= datetime.fromisoformat(marker["completed_at"]):
        fail("freeze timestamp does not precede Test completion")
    if freeze["test_retrieval_run_at_freeze"] is not False or marker["test_was_not_used_for_selection"] is not True:
        fail("freeze/Test integrity flags are incorrect")
    if freeze["questions_sha256"] != sha256(ROOT / "benchmark" / "questions.json"):
        fail("questions changed after freeze")
    for relative_path, expected in freeze["frozen_artifacts_sha256"].items():
        if sha256(ROOT / relative_path) != expected:
            fail(f"frozen artifact changed: {relative_path}")
    for filename, expected in freeze["code_files_sha256"].items():
        path = ROOT / "starter" / "scripts" / filename if filename == "run_benchmark.py" else ROOT / "starter" / "src" / filename
        if sha256(path) != expected:
            fail(f"frozen code changed: {filename}")

    coherence = read_csv(RESULTS / "coherence_audit.csv")
    if len(coherence) != 30:
        fail("coherence audit must contain 10 positions x 3 strategies")
    for strategy in ("A", "B", "C"):
        rows = [row for row in coherence if row["strategy"] == strategy]
        if len(rows) != 10 or len({row["position_id"] for row in rows}) != 10:
            fail(f"coherence coverage invalid for {strategy}")
        if any(row["score_0_2"] not in {"0", "1", "2"} or not row["rationale"] for row in rows):
            fail(f"coherence label/rationale invalid for {strategy}")
    for position in {row["position_id"] for row in coherence}:
        b = next(row for row in coherence if row["position_id"] == position and row["strategy"] == "B")
        c = next(row for row in coherence if row["position_id"] == position and row["strategy"] == "C")
        if b["chunk_id"] != c["chunk_id"] or b["score_0_2"] != c["score_0_2"]:
            fail(f"B/C coherence differs at {position}")

    metadata = read_csv(RESULTS / "metadata_audit.csv")
    if len(metadata) != 45:
        fail("metadata audit must contain 5 Test x top-3 x 3 strategies")
    if any(row["metadata_complete"] != "true" or row["metadata_correct"] != "true" for row in metadata):
        fail("metadata audit contains an incomplete or incorrect record")
    filtered = [row for row in metadata if row["filter_compliant"] != "N/A"]
    if len(filtered) != 6 or any(row["filter_compliant"] != "true" for row in filtered):
        fail("expected 6/6 compliant filtered Test hits")

    grounding = read_csv(RESULTS / "grounding_audit.csv")
    if len(grounding) != 15:
        fail("grounding audit must contain 5 Test x 3 strategies")
    if any(row["score_0_2"] not in {"0", "1", "2"} or not row["rationale"] for row in grounding):
        fail("grounding label/rationale invalid")
    if not any(row["automatic_evidence_hit_at_3"] == "false" for row in grounding):
        fail("grounding audit does not preserve the Q18 automatic metric distinction")

    experiments = read_csv(ROOT / "artifacts" / "experiment_log.csv")
    if {row["strategy"] for row in experiments} != {"A", "B", "C"} or len(experiments) != 3:
        fail("experiment log must contain A/B/C")
    comparison = (RESULTS / "strategy_comparison.md").read_text(encoding="utf-8")
    if "Q10" not in comparison or "Q18" not in comparison or "A–B" not in comparison or "B–C" not in comparison:
        fail("strategy comparison lacks required controlled comparisons/failures")

    print(
        "CP4 validation OK: 60 traces/180 hits, 6 metric rows, B frozen before one-time "
        "Test, 30 coherence labels, 45 metadata records, 15 grounding labels."
    )


if __name__ == "__main__":
    main()
