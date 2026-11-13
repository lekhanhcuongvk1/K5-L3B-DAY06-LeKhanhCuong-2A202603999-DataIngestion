from __future__ import annotations

import unittest

from starter.src.evaluation import evaluate_query, summarize


QUESTION = {
    "id": "QX", "split": "dev", "question": "Question?",
    "expected_answer": "Answer", "gold_source_path": "source.txt",
    "gold_unit_id": "unit-1", "evidence_quote": "complete evidence",
    "filter": None,
}


def hit(source: str, unit: str, text: str, rank: int = 1) -> dict:
    return {
        "rank": rank, "chunk_id": f"c{rank}", "text": text, "score": 0.9,
        "document_id": "doc", "source": source, "page": None,
        "unit_id": unit, "sequence": 1, "char_start": 0,
        "char_end": len(text), "metadata": {},
    }


class EvaluationTests(unittest.TestCase):
    def test_full_evidence_and_source_unit_are_both_required(self) -> None:
        trace = evaluate_query(QUESTION, [
            hit("wrong.txt", "unit-1", "complete evidence", 1),
            hit("source.txt", "unit-1", "incomplete", 2),
            hit("source.txt", "unit-1", "prefix complete evidence suffix", 3),
        ])
        self.assertFalse(trace["hit_at_1"])
        self.assertTrue(trace["evidence_hit_at_3"])
        self.assertEqual(
            [row["evidence_reason"] for row in trace["retrieved_top3"]],
            ["wrong_source_or_unit", "gold_source_unit_but_incomplete_evidence",
             "full_evidence_in_gold_source_unit"],
        )

    def test_summary_reports_numerators_and_denominators(self) -> None:
        traces = [
            {"strategy": "A", "split": "dev", "hit_at_1": True,
             "evidence_hit_at_3": True},
            {"strategy": "A", "split": "dev", "hit_at_1": False,
             "evidence_hit_at_3": True},
        ]
        row = summarize(traces)["metrics"][0]
        self.assertEqual((row["hit_at_1_n"], row["hit_at_1_N"]), (1, 2))
        self.assertEqual((row["evidence_hit_at_3_n"], row["evidence_hit_at_3_N"]), (2, 2))


if __name__ == "__main__":
    unittest.main()
