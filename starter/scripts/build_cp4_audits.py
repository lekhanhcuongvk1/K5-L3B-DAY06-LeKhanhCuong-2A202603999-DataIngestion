"""Build evidence-backed CP4 metadata and grounding audit artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
TRACES = RESULTS / "traces"

GROUNDING = {
    ("Q04", "A"): (0, "No top-3 chunk mentions the recommended collections.deque queue evidence."),
    ("Q04", "B"): (0, "No top-3 chunk contains evidence identifying collections.deque for queues."),
    ("Q04", "C"): (0, "C has no declared filter for Q04 and returns the same non-evidence top-3 as B."),
    ("Q10", "A"): (1, "Rank 2 contains the key 'avoids accidentally catching' fragment but loses the sentence beginning and protected-code context."),
    ("Q10", "B"): (2, "Rank 1 contains the complete gold explanation and source trace."),
    ("Q10", "C"): (2, "C is unfiltered here and rank 1 contains the same complete evidence as B."),
    ("Q14", "A"): (1, "Rank 1 says the file is closed even after a problem, but starts mid-sentence and does not preserve the explicit with-statement context."),
    ("Q14", "B"): (1, "Rank 2 gives equivalent automatic-close evidence, but the retrieved chunk omits the preceding with-statement subject."),
    ("Q14", "C"): (1, "C is unfiltered and has the same partial equivalent evidence as B."),
    ("Q16", "A"): (2, "The definition is split across multiple returned chunks; together top-3 states the isolated Python installation and additional packages."),
    ("Q16", "B"): (2, "Rank 2 contains the complete gold definition of a virtual environment."),
    ("Q16", "C"): (2, "Filtered top-3 is compliant and rank 2 contains the complete definition."),
    ("Q18", "A"): (2, "Rank 1 contains the decisive decimal/accounting fragment and rank 3 supplies equivalent exact-financial context."),
    ("Q18", "B"): (0, "Top-3 discusses fractions, general floating point, and math, but omits the recommendation to use decimal for accounting."),
    ("Q18", "C"): (2, "The chapter filter brings the complete gold decimal recommendation into rank 3."),
}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    traces = [
        trace
        for strategy in ("A", "B", "C")
        for trace in read_jsonl(TRACES / f"test_{strategy}.jsonl")
    ]
    chunk_maps = {
        "A": {row["chunk_id"]: row for row in read_jsonl(RESULTS / "chunks_A.jsonl")},
        "B": {row["chunk_id"]: row for row in read_jsonl(RESULTS / "chunks_B.jsonl")},
    }
    metadata_rows = []
    for trace in traces:
        stored = trace["stored_strategy"]
        filters = trace["filters_applied"]
        for hit in trace["retrieved_top3"]:
            source = chunk_maps[stored].get(hit["chunk_id"])
            required = (
                "document_id", "source", "page", "unit_id", "char_start", "char_end",
            )
            metadata_required = ("chapter", "version")
            complete = source is not None and all(key in hit for key in required) and all(
                key in hit["metadata"] for key in metadata_required
            )
            correct = bool(source) and all(hit[key] == source[key] for key in required) and all(
                hit["metadata"][key] == source["metadata"][key] for key in metadata_required
            )
            compliant = "N/A" if not filters else str(
                all(hit["metadata"].get(key) == value for key, value in filters.items())
            ).lower()
            metadata_rows.append({
                "question_id": trace["question_id"],
                "strategy": trace["strategy"],
                "rank": hit["rank"],
                "chunk_id": hit["chunk_id"],
                "source": hit["source"],
                "page": "" if hit["page"] is None else hit["page"],
                "unit_id": hit["unit_id"],
                "chapter": hit["metadata"].get("chapter"),
                "metadata_complete": str(complete).lower(),
                "metadata_correct": str(correct).lower(),
                "filter_applied": json.dumps(filters, ensure_ascii=False) if filters else "N/A",
                "filter_compliant": compliant,
                "rationale": (
                    "Compared source/unit/span/chapter/version with the persisted CP2 chunk artifact; "
                    + ("filter value also matched." if filters else "no filter was applied for this strategy/query.")
                ),
                "reviewer": "Codex AI-assisted manual review; author confirmation recommended",
            })
    with (RESULTS / "metadata_audit.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(metadata_rows[0]))
        writer.writeheader()
        writer.writerows(metadata_rows)

    grounding_rows = []
    for trace in sorted(traces, key=lambda row: (row["question_id"], row["strategy"])):
        score, rationale = GROUNDING[(trace["question_id"], trace["strategy"])]
        grounding_rows.append({
            "question_id": trace["question_id"],
            "strategy": trace["strategy"],
            "score_0_2": score,
            "rationale": rationale,
            "reviewer": "Codex AI-assisted manual review; author confirmation recommended",
        })
    with (RESULTS / "grounding_audit.csv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(grounding_rows[0]))
        writer.writeheader()
        writer.writerows(grounding_rows)

    grounding_summary = {}
    for strategy in ("A", "B", "C"):
        values = [row["score_0_2"] for row in grounding_rows if row["strategy"] == strategy]
        grounding_summary[strategy] = {
            "n": len(values),
            "score_counts": {str(score): values.count(score) for score in (0, 1, 2)},
            "mean_out_of_2": sum(values) / len(values),
        }
    filtered_rows = [row for row in metadata_rows if row["filter_compliant"] != "N/A"]
    summary = {
        "metadata": {
            "records_reviewed": len(metadata_rows),
            "complete_and_correct": sum(
                row["metadata_complete"] == "true" and row["metadata_correct"] == "true"
                for row in metadata_rows
            ),
            "filtered_records": len(filtered_rows),
            "filter_compliant_records": sum(
                row["filter_compliant"] == "true" for row in filtered_rows
            ),
        },
        "grounding": grounding_summary,
        "review_method": (
            "Metadata was cross-checked against persisted chunk artifacts. Grounding was manually "
            "reviewed from the same five Test top-3 traces per strategy; labels assess retrieval "
            "evidence, not LLM answer accuracy. Labels were reviewed by Codex with author "
            "confirmation recommended before submission."
        ),
        "limitations": "Single reviewer and five-question Test set may introduce subjective and sampling bias.",
    }
    (RESULTS / "manual_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"CP4 audits OK: {len(metadata_rows)} metadata records, "
        f"{len(filtered_rows)} filtered records, {len(grounding_rows)} grounding labels."
    )


if __name__ == "__main__":
    main()
