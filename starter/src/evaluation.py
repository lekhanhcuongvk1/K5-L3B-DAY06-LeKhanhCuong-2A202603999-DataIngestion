"""Evaluate full-evidence retrieval and preserve auditable per-query traces."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def canonical_evidence(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace('"', "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Require the declared source/unit and the complete evidence quotation.

    Accept any documented alternative gold evidence. Do not infer human grounding
    or chunk coherence labels from exact string match.
    """
    golds = [{
        "source": question["gold_source_path"],
        "unit_id": question["gold_unit_id"],
        "evidence_quote": question["evidence_quote"],
    }, *question.get("alternative_golds", [])]
    evaluated_hits: list[dict[str, Any]] = []
    for hit in hits:
        matched_gold = None
        reason = "wrong_source_or_unit"
        for gold in golds:
            if hit["source"] != gold["source"] or hit["unit_id"] != gold["unit_id"]:
                continue
            if canonical_evidence(gold["evidence_quote"]) in canonical_evidence(hit["text"]):
                matched_gold = gold
                reason = "full_evidence_in_gold_source_unit"
                break
            reason = "gold_source_unit_but_incomplete_evidence"
        evaluated = dict(hit)
        evaluated["evidence_hit"] = matched_gold is not None
        evaluated["evidence_reason"] = reason
        evaluated_hits.append(evaluated)
    return {
        "question_id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_source_path": question["gold_source_path"],
        "gold_unit_id": question["gold_unit_id"],
        "evidence_quote": question["evidence_quote"],
        "filters_declared": question["filter"],
        "retrieved_top3": evaluated_hits,
        "hit_at_1": bool(evaluated_hits and evaluated_hits[0]["evidence_hit"]),
        "evidence_hit_at_3": any(hit["evidence_hit"] for hit in evaluated_hits[:3]),
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 and Evidence Hit@3 with explicit numerators."""
    if not traces:
        raise ValueError("Cannot summarize an empty trace list")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for trace in traces:
        groups.setdefault((trace["strategy"], trace["split"]), []).append(trace)
    rows = []
    for (strategy, split), group in sorted(groups.items()):
        total = len(group)
        hit1 = sum(bool(trace["hit_at_1"]) for trace in group)
        hit3 = sum(bool(trace["evidence_hit_at_3"]) for trace in group)
        rows.append({
            "strategy": strategy,
            "split": split,
            "questions": total,
            "hit_at_1_n": hit1,
            "hit_at_1_N": total,
            "hit_at_1_rate": hit1 / total,
            "evidence_hit_at_3_n": hit3,
            "evidence_hit_at_3_N": total,
            "evidence_hit_at_3_rate": hit3 / total,
        })
    return {"metrics": rows}
