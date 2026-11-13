"""Compare frozen embedding candidates on Strategy B and Dev only."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
STARTER = ROOT / "starter"
if str(STARTER) not in sys.path:
    sys.path.insert(0, str(STARTER))

from src.chunking import by_paragraph  # noqa: E402
from src.embeddings import MyEmbedder  # noqa: E402
from src.evaluation import evaluate_query  # noqa: E402
from src.ingestion import load_text_manifest  # noqa: E402
from src.store import PgVectorStore  # noqa: E402


CANDIDATES = {
    "multilingual_minilm": {
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "table": "day06_chunks_vi_minilm_dev",
    },
    "vietnamese_bkai": {
        "model": "bkai-foundation-models/vietnamese-bi-encoder",
        "table": "day06_chunks_vi_bkai_dev",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    load_dotenv(STARTER / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is missing")
    split = json.loads((ROOT / "benchmark" / "split_manifest.json").read_text(encoding="utf-8"))
    questions_path = ROOT / "benchmark" / "questions.json"
    if sha256(questions_path) != split["questions_sha256"]:
        raise SystemExit("Frozen questions checksum mismatch")
    benchmark = json.loads(questions_path.read_text(encoding="utf-8"))
    dev_questions = [row for row in benchmark["questions"] if row["split"] == "dev"]
    if len(dev_questions) != 15:
        raise SystemExit("Model bake-off requires exactly the 15 frozen Dev questions")
    units, errors = load_text_manifest(ROOT / "data" / "manifest.json")
    if errors:
        raise SystemExit(f"Corpus loader returned {len(errors)} errors")
    chunks = [chunk for unit in units for chunk in by_paragraph(unit, 1_000)]

    candidate_results: list[dict[str, object]] = []
    all_traces: list[dict[str, object]] = []
    for candidate, config in CANDIDATES.items():
        started = time.perf_counter()
        model_started = time.perf_counter()
        embedder = MyEmbedder(str(config["model"]), device="cpu", batch_size=32)
        model_load_seconds = time.perf_counter() - model_started
        document_started = time.perf_counter()
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        document_embedding_seconds = time.perf_counter() - document_started
        store = PgVectorStore(
            database_url, embedder.dimensions, table_name=str(config["table"])
        )
        store.create_schema()
        upsert_started = time.perf_counter()
        store.upsert("B", chunks, vectors)
        first_count = store.count("B")
        store.upsert("B", chunks, vectors)
        second_count = store.count("B")
        upsert_seconds = time.perf_counter() - upsert_started
        if first_count != len(chunks) or second_count != len(chunks):
            raise RuntimeError(f"{candidate} idempotence/count failure")

        traces = []
        query_times = []
        retrieval_times = []
        for question in dev_questions:
            query_started = time.perf_counter()
            query_vector = embedder.embed_query(question["question"])
            query_times.append((time.perf_counter() - query_started) * 1_000)
            retrieval_started = time.perf_counter()
            hits = store.search("B", query_vector, top_k=3)
            retrieval_times.append((time.perf_counter() - retrieval_started) * 1_000)
            trace = evaluate_query(question, hits)
            trace["candidate"] = candidate
            trace["strategy"] = "B"
            traces.append(trace)
            all_traces.append(trace)

        hit1 = sum(bool(trace["hit_at_1"]) for trace in traces)
        hit3 = sum(bool(trace["evidence_hit_at_3"]) for trace in traces)
        candidate_results.append({
            "candidate": candidate,
            "model": config["model"],
            "table": config["table"],
            "dimensions": embedder.dimensions,
            "dev_questions": len(traces),
            "hit_at_1_n": hit1,
            "hit_at_1_N": len(traces),
            "evidence_hit_at_3_n": hit3,
            "evidence_hit_at_3_N": len(traces),
            "mean_query_embedding_ms": round(sum(query_times) / len(query_times), 3),
            "mean_retrieval_ms": round(sum(retrieval_times) / len(retrieval_times), 3),
            "model_load_seconds": round(model_load_seconds, 3),
            "document_embedding_seconds": round(document_embedding_seconds, 3),
            "two_upsert_passes_seconds": round(upsert_seconds, 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "cost_usd": 0,
            "stored_chunk_count_after_each_upsert": [first_count, second_count],
        })

    ranked = sorted(
        candidate_results,
        key=lambda row: (
            int(row["evidence_hit_at_3_n"]), int(row["hit_at_1_n"]),
            -float(row["mean_query_embedding_ms"]), -float(row["mean_retrieval_ms"]),
        ),
        reverse=True,
    )
    selected = ranked[0]
    payload = {
        "stage": "CP3 model bake-off on frozen Dev only; Test unopened",
        "strategy": "B paragraph-aware max 1000, no filter",
        "selection_rule": split["model_selection_rule"],
        "questions_sha256": split["questions_sha256"],
        "test_retrieval_run": False,
        "candidates": candidate_results,
        "ranking": [row["candidate"] for row in ranked],
        "selected_candidate": selected["candidate"],
        "selected_model": selected["model"],
        "selected_dimensions": selected["dimensions"],
    }
    results = ROOT / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "model_bakeoff_dev.json").write_text(
        json.dumps({"summary": payload, "traces": all_traces}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    (results / "model_selection.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(
        "Model bake-off complete on Dev only: "
        + "; ".join(
            f"{row['candidate']} Hit@1={row['hit_at_1_n']}/15 Hit@3={row['evidence_hit_at_3_n']}/15"
            for row in candidate_results
        )
        + f"; selected={selected['candidate']}; Test unopened."
    )


if __name__ == "__main__":
    main()
