"""CP3 ingestion and smoke retrieval entry point (Dev-only, no benchmark run)."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .ingestion import load_text_manifest
from .store import PgVectorStore


STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
RESULTS = ROOT / "results"
MODEL_DEFAULT = "bkai-foundation-models/vietnamese-bi-encoder"
MODEL_REVISION = "84f9d9ada0d1a3c37557398b9ae9fcedcdf40be0"
MODEL_LICENSE = "Apache-2.0"
TABLE_NAME = "day06_chunks_vi"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def main() -> None:
    """Embed A/B once, persist them, and smoke-test A/B/C using Dev only."""
    load_dotenv(STARTER / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL missing; copy starter/.env.example to starter/.env")
    model_name = os.getenv("EMBEDDING_MODEL") or MODEL_DEFAULT
    if model_name != MODEL_DEFAULT:
        raise SystemExit(
            f"EMBEDDING_MODEL={model_name!r} differs from the frozen Vietnamese model "
            f"{MODEL_DEFAULT!r}; update starter/.env before CP3"
        )
    selection_path = RESULTS / "model_selection.json"
    if not selection_path.is_file():
        raise SystemExit("results/model_selection.json is required before official CP3 indexing")
    model_selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if model_selection.get("selected_model") != model_name:
        raise SystemExit("EMBEDDING_MODEL differs from the frozen Dev-only model selection")

    started = time.perf_counter()
    units, processing_errors = load_text_manifest(ROOT / "data" / "manifest.json")
    if processing_errors:
        raise SystemExit(f"Refusing to embed corpus with {len(processing_errors)} processing errors")
    chunks_a = [chunk for unit in units for chunk in fixed_size(unit, 500, 50)]
    chunks_b = [chunk for unit in units for chunk in by_paragraph(unit, 1_000)]

    model_started = time.perf_counter()
    embedder = MyEmbedder(model_name=model_name, device="cpu", batch_size=32)
    model_load_seconds = time.perf_counter() - model_started
    embedding_started = time.perf_counter()
    vectors_a = embedder.embed_documents([chunk.text for chunk in chunks_a])
    vectors_b = embedder.embed_documents([chunk.text for chunk in chunks_b])
    embedding_seconds = time.perf_counter() - embedding_started

    store = PgVectorStore(database_url, embedder.dimensions, table_name=TABLE_NAME)
    store.create_schema()
    ingestion_started = time.perf_counter()
    store.upsert("A", chunks_a, vectors_a)
    store.upsert("B", chunks_b, vectors_b)
    first_counts = {"A": store.count("A"), "B": store.count("B")}
    store.upsert("A", chunks_a, vectors_a)
    store.upsert("B", chunks_b, vectors_b)
    second_counts = {"A": store.count("A"), "B": store.count("B")}
    ingestion_seconds = time.perf_counter() - ingestion_started
    expected_counts = {"A": len(chunks_a), "B": len(chunks_b)}
    if first_counts != expected_counts or second_counts != expected_counts:
        raise RuntimeError(
            f"Idempotence failed: expected {expected_counts}, got {first_counts} then {second_counts}"
        )

    benchmark = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    smoke_ids = {"Q01", "Q04", "Q10"}
    smoke_questions = [
        question
        for question in benchmark["questions"]
        if question["split"] == "dev" and question["id"] in smoke_ids
    ]
    if {question["id"] for question in smoke_questions} != smoke_ids:
        raise RuntimeError("Expected Dev smoke questions are missing")

    smoke_traces: list[dict[str, object]] = []
    for question in smoke_questions:
        query_vector = embedder.embed_query(question["question"])
        for strategy, stored_strategy, filters in (
            ("A", "A", None),
            ("B", "B", None),
            ("C", "B", question["filter"]),
        ):
            retrieval_started = time.perf_counter()
            hits = store.search(stored_strategy, query_vector, top_k=3, filters=filters)
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1_000
            if len(hits) != 3:
                raise RuntimeError(f"{strategy}/{question['id']} returned {len(hits)} hits")
            if filters and any(
                any(hit["metadata"].get(key) != value for key, value in filters.items())
                for hit in hits
            ):
                raise RuntimeError(f"C/{question['id']} violated its collection filter")
            smoke_traces.append(
                {
                    "question_id": question["id"],
                    "split": "dev",
                    "question": question["question"],
                    "strategy": strategy,
                    "stored_strategy": stored_strategy,
                    "filters_applied": filters,
                    "retrieval_ms": round(retrieval_ms, 3),
                    "top3": hits,
                }
            )

    for question in smoke_questions:
        if question["filter"] is None:
            trace_b = next(
                trace for trace in smoke_traces
                if trace["question_id"] == question["id"] and trace["strategy"] == "B"
            )
            trace_c = next(
                trace for trace in smoke_traces
                if trace["question_id"] == question["id"] and trace["strategy"] == "C"
            )
            if [hit["chunk_id"] for hit in trace_b["top3"]] != [
                hit["chunk_id"] for hit in trace_c["top3"]
            ]:
                raise RuntimeError("B and C differ for an unfiltered deterministic query")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "smoke_retrieval.json").write_text(
        json.dumps(smoke_traces, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    run_metadata = {
        "stage": "CP3 Dev-only smoke; Test retrieval not run",
        "model": {
            "provider": "local Sentence Transformers",
            "name": model_name,
            "revision": MODEL_REVISION,
            "license": MODEL_LICENSE,
            "dimensions": embedder.dimensions,
            "device": embedder.device,
            "batch_size": embedder.batch_size,
            "normalize_embeddings": True,
            "query_document_processing": "same model and normalization",
            "sentence_transformers_version": package_version("sentence-transformers"),
            "transformers_version": package_version("transformers"),
            "torch_version": package_version("torch"),
        },
        "store": {
            "backend": "PostgreSQL 16 + pgvector 0.8.7",
            "table": store.TABLE,
            "metric": "cosine",
            "search": "exact sequential scan; no approximate index",
            "persistent": True,
        },
        "strategies": {
            "A": {"stored_strategy": "A", "chunking": "fixed 500/overlap 50", "filter": False},
            "B": {"stored_strategy": "B", "chunking": "paragraph-aware max 1000", "filter": False},
            "C": {"stored_strategy": "B", "chunking": "identical to B/shared index", "filter": "question.collection when supplied"},
        },
        "counts": {
            "source_units": len(units),
            "A": len(chunks_a),
            "B": len(chunks_b),
            "C_physical_rows": 0,
            "C_shared_with": "B",
            "after_first_upsert": first_counts,
            "after_second_upsert": second_counts,
        },
        "timing_seconds": {
            "model_load": round(model_load_seconds, 3),
            "embedding_A_and_B": round(embedding_seconds, 3),
            "two_upsert_passes_A_and_B": round(ingestion_seconds, 3),
            "total": round(time.perf_counter() - started, 3),
        },
        "cost_usd": 0,
        "benchmark_integrity": {
            "questions_sha256": file_sha256(ROOT / "benchmark" / "questions.json"),
            "smoke_question_ids": sorted(smoke_ids),
            "smoke_split": "dev",
            "test_retrieval_run": False,
            "model_selection_artifact": "results/model_selection.json",
            "model_selection_questions_sha256": model_selection["questions_sha256"],
        },
    }
    (RESULTS / "run_metadata.json").write_text(
        json.dumps(run_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"CP3 smoke OK: model={model_name}, dimensions={embedder.dimensions}, "
        f"A={first_counts['A']}, B={first_counts['B']} (C shares B), "
        f"{len(smoke_traces)} Dev-only top-3 traces, idempotence PASS."
    )
if __name__ == "__main__":
    main()
