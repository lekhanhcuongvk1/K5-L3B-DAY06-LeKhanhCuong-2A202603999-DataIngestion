"""Build evidence-backed metadata and manually reviewed grounding audits."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
TRACES = RESULTS / "traces"

GROUNDING_RATIONALES = {
    "Q16": "Top-3 contains the complete evidence that ALGOL 68 succeeds ALGOL 60 and targets a broader application scope.",
    "Q17": "Top-3 contains the complete evidence that an AutoIt script can become a compressed standalone executable without the interpreter.",
    "Q18": "Top-3 contains equivalent, traceable evidence that AlphaFold predicts protein structure from the amino-acid sequence; exact-quote Hit@3 remains false.",
    "Q19": "Top-3 contains the complete CIFAR image count, 32x32 RGB size, and train/test split evidence.",
    "Q20": "Top-3 contains the complete query-key relevance and weighting evidence needed to answer.",
}


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    traces = [
        row
        for strategy in ("A", "B", "C")
        for row in read_jsonl(TRACES / f"test_{strategy}.jsonl")
    ]
    if len(traces) != 15 or any(row["split"] != "test" for row in traces):
        raise SystemExit("Expected 5 Test traces x 3 strategies")
    chunk_maps = {
        "A": {row["chunk_id"]: row for row in read_jsonl(RESULTS / "chunks_A.jsonl")},
        "B": {row["chunk_id"]: row for row in read_jsonl(RESULTS / "chunks_B.jsonl")},
    }

    metadata_rows = []
    for trace in sorted(traces, key=lambda row: (row["question_id"], row["strategy"])):
        stored = trace["stored_strategy"]
        filters = trace["filters_applied"]
        for hit in trace["retrieved_top3"]:
            source = chunk_maps[stored].get(hit["chunk_id"])
            if source is None:
                raise SystemExit(f"Missing persisted chunk {hit['chunk_id']}")
            metadata_required = ("collection", "version", "title", "canonical_url")
            complete = all(hit["metadata"].get(key) not in (None, "") for key in metadata_required)
            correct = (
                hit["document_id"] == source["document_id"]
                and hit["source"] == source["source"]
                and hit["unit_id"] == source["unit_id"]
                and hit["char_start"] == source["char_start"]
                and hit["char_end"] == source["char_end"]
                and all(hit["metadata"].get(key) == source["metadata"].get(key) for key in metadata_required)
            )
            compliant = "N/A" if not filters else str(
                all(hit["metadata"].get(key) == value for key, value in filters.items())
            ).lower()
            metadata_rows.append({
                "question_id": trace["question_id"], "strategy": trace["strategy"],
                "rank": hit["rank"], "chunk_id": hit["chunk_id"],
                "document_id": hit["document_id"], "source": hit["source"],
                "unit_id": hit["unit_id"], "collection": hit["metadata"].get("collection"),
                "version": hit["metadata"].get("version"),
                "title": hit["metadata"].get("title"),
                "canonical_url": hit["metadata"].get("canonical_url"),
                "metadata_complete": str(complete).lower(),
                "metadata_correct": str(correct).lower(),
                "filter_applied": json.dumps(filters, ensure_ascii=False) if filters else "N/A",
                "filter_compliant": compliant,
                "rationale": (
                    "Compared document/source/unit/span/collection/revision/title/URL with the "
                    "persisted CP2 chunk; " + ("filter value also matched." if filters else "no filter applied.")
                ),
            })
    with (RESULTS / "metadata_audit.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(metadata_rows[0]))
        writer.writeheader()
        writer.writerows(metadata_rows)

    grounding_rows = []
    for trace in sorted(traces, key=lambda row: (row["question_id"], row["strategy"])):
        question_id = trace["question_id"]
        grounding_rows.append({
            "question_id": question_id,
            "strategy": trace["strategy"],
            "score_0_2": 2,
            "rationale": GROUNDING_RATIONALES[question_id],
            "automatic_evidence_hit_at_3": str(trace["evidence_hit_at_3"]).lower(),
            "review_method": "Manual review of complete top-3 text and source trace by Codex; author confirmation recommended",
        })
    with (RESULTS / "grounding_audit.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(grounding_rows[0]))
        writer.writeheader()
        writer.writerows(grounding_rows)

    filtered = [row for row in metadata_rows if row["filter_compliant"] != "N/A"]
    grounding_summary = {}
    for strategy in ("A", "B", "C"):
        values = [row["score_0_2"] for row in grounding_rows if row["strategy"] == strategy]
        grounding_summary[strategy] = {
            "label_distribution": {str(key): Counter(values).get(key, 0) for key in (0, 1, 2)},
            "mean_out_of_2": sum(values) / len(values),
        }
    summary = {
        "metadata": {
            "records_reviewed": len(metadata_rows),
            "complete_and_correct_records": sum(
                row["metadata_complete"] == "true" and row["metadata_correct"] == "true"
                for row in metadata_rows
            ),
            "filtered_records": len(filtered),
            "filter_compliant_records": sum(row["filter_compliant"] == "true" for row in filtered),
        },
        "grounding": grounding_summary,
        "review_method": (
            "Metadata was mechanically cross-checked against persisted chunks. Grounding labels "
            "were assigned after reading complete top-3 Test evidence; Codex labels require author confirmation."
        ),
        "limitations": "Single assisted reviewer and a five-question Test set introduce subjective and sampling bias.",
    }
    (RESULTS / "manual_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"CP4 audits OK: {len(metadata_rows)} metadata records, {len(filtered)} filtered "
        f"records, {len(grounding_rows)} grounding labels."
    )


if __name__ == "__main__":
    main()
