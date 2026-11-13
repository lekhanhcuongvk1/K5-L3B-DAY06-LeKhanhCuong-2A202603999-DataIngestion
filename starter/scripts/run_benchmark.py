"""Run CP4 in integrity-preserving stages: dev, freeze, then one-time test."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter"
if str(STARTER) not in sys.path:
    sys.path.insert(0, str(STARTER))

from src.embeddings import MyEmbedder  # noqa: E402
from src.evaluation import evaluate_query, summarize  # noqa: E402
from src.store import PgVectorStore  # noqa: E402


TRACES_DIR = ROOT / "results" / "traces"
QUESTIONS_PATH = ROOT / "benchmark" / "questions.json"
SPLIT_PATH = ROOT / "benchmark" / "split_manifest.json"
RUN_METADATA_PATH = ROOT / "results" / "run_metadata.json"
DEV_METRICS_PATH = ROOT / "results" / "retrieval_metrics_dev.json"
ALL_METRICS_PATH = ROOT / "results" / "retrieval_metrics.csv"
FREEZE_PATH = ROOT / "results" / "strategy_freeze.json"
COHERENCE_PATH = ROOT / "results" / "coherence_audit.csv"
TEST_MARKER_PATH = ROOT / "results" / ".test_completed"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_runtime() -> tuple[MyEmbedder, PgVectorStore, dict, dict, dict]:
    load_dotenv(STARTER / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is missing")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    run_metadata = json.loads(RUN_METADATA_PATH.read_text(encoding="utf-8"))
    if sha256(QUESTIONS_PATH) != split["questions_sha256"]:
        raise SystemExit("Frozen questions checksum mismatch")
    model = run_metadata["model"]
    embedder = MyEmbedder(model["name"], device=model["device"], batch_size=model["batch_size"])
    store = PgVectorStore(database_url, embedder.dimensions)
    return embedder, store, questions, split, run_metadata


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def retrieve_split(split_name: str) -> list[dict]:
    embedder, store, benchmark, _, _ = load_runtime()
    questions = [q for q in benchmark["questions"] if q["split"] == split_name]
    traces: list[dict] = []
    for question in questions:
        query_started = time.perf_counter()
        vector = embedder.embed_query(question["question"])
        embedding_ms = (time.perf_counter() - query_started) * 1_000
        for strategy, stored_strategy, filters in (
            ("A", "A", None),
            ("B", "B", None),
            ("C", "B", question["filter"]),
        ):
            retrieval_started = time.perf_counter()
            hits = store.search(stored_strategy, vector, top_k=3, filters=filters)
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1_000
            trace = evaluate_query(question, hits)
            trace.update({
                "strategy": strategy,
                "stored_strategy": stored_strategy,
                "filters_applied": filters,
                "query_embedding_ms": round(embedding_ms, 3),
                "retrieval_ms": round(retrieval_ms, 3),
                "error": None,
            })
            traces.append(trace)
    return traces


def run_dev() -> None:
    if FREEZE_PATH.exists() or TEST_MARKER_PATH.exists():
        raise SystemExit("Dev cannot be rerun after strategy freeze/Test without an explicit integrity reset")
    traces = retrieve_split("dev")
    for strategy in ("A", "B", "C"):
        write_jsonl(
            TRACES_DIR / f"dev_{strategy}.jsonl",
            [trace for trace in traces if trace["strategy"] == strategy],
        )
    metrics = summarize(traces)
    DEV_METRICS_PATH.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("DEV complete; Test remains unopened:", metrics["metrics"])


def load_coherence_means() -> dict[str, float]:
    if not COHERENCE_PATH.is_file():
        raise SystemExit("coherence_audit.csv is required before freeze for tie-breaking")
    scores: dict[str, list[int]] = {"A": [], "B": [], "C": []}
    with COHERENCE_PATH.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            scores[row["strategy"]].append(int(row["score_0_2"]))
    if any(len(values) != 10 for values in scores.values()):
        raise SystemExit("Coherence audit must contain 10 positions for each strategy")
    return {strategy: sum(values) / len(values) for strategy, values in scores.items()}


def freeze_strategy() -> None:
    if FREEZE_PATH.exists() or TEST_MARKER_PATH.exists():
        raise SystemExit("Strategy is already frozen or Test has already run")
    metrics_payload = json.loads(DEV_METRICS_PATH.read_text(encoding="utf-8"))
    metrics = {row["strategy"]: row for row in metrics_payload["metrics"]}
    coherence = load_coherence_means()
    run_metadata = json.loads(RUN_METADATA_PATH.read_text(encoding="utf-8"))
    # B is operationally simpler than C when retrieval/coherence/storage tie:
    # C adds a conditional filter path. A is between them for this final
    # tie-break because it has a separate, larger index but no filter logic.
    complexity_preference = {"B": 2, "A": 1, "C": 0}
    ranked = sorted(
        ("A", "B", "C"),
        key=lambda strategy: (
            metrics[strategy]["evidence_hit_at_3_rate"],
            coherence[strategy],
            -run_metadata["counts"]["A" if strategy == "A" else "B"],
            complexity_preference[strategy],
        ),
        reverse=True,
    )
    selected = ranked[0]
    payload = {
        "frozen_at": now(),
        "stage": "after full Dev evaluation and before any Test retrieval",
        "selected_strategy": selected,
        "ranking": ranked,
        "selection_rule": json.loads(SPLIT_PATH.read_text(encoding="utf-8"))["strategy_selection_rule"],
        "dev_metrics": metrics_payload["metrics"],
        "coherence_mean_by_strategy": coherence,
        "questions_sha256": sha256(QUESTIONS_PATH),
        "code_files_sha256": {
            "embeddings.py": sha256(STARTER / "src" / "embeddings.py"),
            "store.py": sha256(STARTER / "src" / "store.py"),
            "evaluation.py": sha256(STARTER / "src" / "evaluation.py"),
            "run_benchmark.py": sha256(Path(__file__)),
        },
        "model": run_metadata["model"],
        "strategies": run_metadata["strategies"],
        "test_retrieval_run_at_freeze": False,
    }
    FREEZE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Strategy frozen before Test: {selected}; ranking={ranked}")


def verify_freeze() -> dict:
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if freeze["questions_sha256"] != sha256(QUESTIONS_PATH):
        raise SystemExit("Questions changed after strategy freeze")
    for filename, expected in freeze["code_files_sha256"].items():
        path = Path(__file__) if filename == "run_benchmark.py" else STARTER / "src" / filename
        if sha256(path) != expected:
            raise SystemExit(f"{filename} changed after strategy freeze")
    return freeze


def run_test() -> None:
    if not FREEZE_PATH.is_file():
        raise SystemExit("Refusing Test: strategy_freeze.json does not exist")
    if TEST_MARKER_PATH.exists():
        raise SystemExit("Refusing Test rerun: one-time Test marker already exists")
    freeze = verify_freeze()
    traces = retrieve_split("test")
    for strategy in ("A", "B", "C"):
        write_jsonl(
            TRACES_DIR / f"test_{strategy}.jsonl",
            [trace for trace in traces if trace["strategy"] == strategy],
        )
    all_traces = []
    for split in ("dev", "test"):
        for strategy in ("A", "B", "C"):
            all_traces.extend(read_jsonl(TRACES_DIR / f"{split}_{strategy}.jsonl"))
    metrics = summarize(all_traces)["metrics"]
    with ALL_METRICS_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(metrics[0]))
        writer.writeheader()
        writer.writerows(metrics)
    TEST_MARKER_PATH.write_text(
        json.dumps({
            "completed_at": now(),
            "selected_strategy_before_test": freeze["selected_strategy"],
            "test_question_count": 5,
            "test_was_not_used_for_selection": True,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("One-time TEST complete; no tuning permitted:", metrics)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("dev", "freeze", "test"))
    args = parser.parse_args()
    {"dev": run_dev, "freeze": freeze_strategy, "test": run_test}[args.stage]()


if __name__ == "__main__":
    main()
