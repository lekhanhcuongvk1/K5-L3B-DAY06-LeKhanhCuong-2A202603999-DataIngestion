"""Validate and freeze the CP1 gold benchmark without running retrieval."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "benchmark" / "questions.json"
SPLIT_PATH = ROOT / "benchmark" / "split_manifest.json"
CORPUS_MANIFEST_PATH = ROOT / "data" / "manifest.json"
REQUIRED_FIELDS = {
    "id",
    "split",
    "type",
    "question",
    "expected_answer",
    "gold_source_id",
    "gold_source_path",
    "gold_page",
    "gold_unit_id",
    "evidence_quote",
    "filter",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path.relative_to(ROOT)}: {exc}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_normalizer():
    path = ROOT / "starter" / "scripts" / "build_manifest.py"
    spec = importlib.util.spec_from_file_location("build_manifest", path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load the corpus normalizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.normalize_text


def canonical_evidence(text: str) -> str:
    """Ignore line wrapping and plain-text markup, but preserve wording/punctuation."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace('"', "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def validate(freeze: bool = False) -> dict[str, int]:
    benchmark = load_json(QUESTIONS_PATH)
    split_manifest = load_json(SPLIT_PATH)
    corpus_manifest = load_json(CORPUS_MANIFEST_PATH)
    questions = benchmark.get("questions")
    if not isinstance(questions, list):
        raise ValueError("questions must be a list")
    if benchmark.get("benchmark_id") != split_manifest.get("benchmark_id"):
        raise ValueError("benchmark_id differs between questions and split manifest")

    units = {unit["unit_id"]: unit for unit in corpus_manifest["units"]}
    filter_field = corpus_manifest["filter_metadata"]["field"]
    filter_values = set(corpus_manifest["filter_metadata"]["distinct_values"])
    normalize_text = load_normalizer()
    normalized_sources: dict[str, str] = {}
    errors: list[str] = []
    ids: list[str] = []
    split_ids = {"dev": [], "test": []}
    filter_count = 0
    test_filter_count = 0

    for index, question in enumerate(questions, start=1):
        label = question.get("id", f"row-{index}") if isinstance(question, dict) else f"row-{index}"
        if not isinstance(question, dict):
            errors.append(f"{label}: question must be an object")
            continue
        missing = REQUIRED_FIELDS - set(question)
        if missing:
            errors.append(f"{label}: missing fields {sorted(missing)}")
            continue
        ids.append(question["id"])
        split = question["split"]
        if split not in split_ids:
            errors.append(f"{label}: invalid split {split!r}")
        else:
            split_ids[split].append(question["id"])
        if not all(isinstance(question[field], str) and question[field].strip()
                   for field in ("id", "type", "question", "expected_answer", "gold_source_id",
                                 "gold_source_path", "gold_unit_id", "evidence_quote")):
            errors.append(f"{label}: required text fields must be non-empty strings")
        if question["gold_page"] is not None:
            errors.append(f"{label}: non-paginated corpus requires gold_page=null")

        unit = units.get(question["gold_unit_id"])
        if unit is None:
            errors.append(f"{label}: unknown gold_unit_id {question['gold_unit_id']!r}")
            continue
        if question["gold_source_id"] != unit.get("source_id"):
            errors.append(f"{label}: gold_source_id does not match its unit")
        if unit["source_path"] != question["gold_source_path"]:
            errors.append(f"{label}: gold source path does not match its unit")
            continue
        source_path = ROOT / question["gold_source_path"]
        if not source_path.is_file():
            errors.append(f"{label}: missing source file")
            continue
        if question["gold_source_path"] not in normalized_sources:
            normalized_sources[question["gold_source_path"]] = normalize_text(
                source_path.read_text(encoding="utf-8")
            )
        source_text = normalized_sources[question["gold_source_path"]]
        unit_text = source_text[unit["normalized_start"]:unit["normalized_end"]]
        if canonical_evidence(question["evidence_quote"]) not in canonical_evidence(unit_text):
            errors.append(f"{label}: evidence is not contained in the declared gold unit")

        filters = question["filter"]
        if filters is not None:
            filter_count += 1
            if split == "test":
                test_filter_count += 1
            if not isinstance(filters, dict) or set(filters) != {filter_field}:
                errors.append(f"{label}: filter must be null or a {filter_field}-only object")
            elif filters[filter_field] not in filter_values:
                errors.append(f"{label}: {filter_field} value is absent from the corpus")
            elif filters[filter_field] != unit[filter_field]:
                errors.append(f"{label}: {filter_field} filter does not match the gold unit")

    if len(ids) != len(set(ids)):
        errors.append("Question IDs are not unique")
    if len(questions) < 20:
        errors.append("Benchmark must contain at least 20 questions")
    if len(split_ids["dev"]) < 15 or len(split_ids["test"]) < 5:
        errors.append("Split requires at least 15 Dev and 5 Test questions")
    if filter_count < 3 or test_filter_count < 1:
        errors.append("At least 3 filter questions are required, including 1 Test question")
    if split_ids["dev"] != split_manifest.get("dev_question_ids"):
        errors.append("Dev IDs/order differ from split_manifest.json")
    if split_ids["test"] != split_manifest.get("test_question_ids"):
        errors.append("Test IDs/order differ from split_manifest.json")

    positions = split_manifest.get("coherence_positions")
    if not isinstance(positions, list) or len(positions) != 10:
        errors.append("Exactly 10 coherence positions must be frozen")
    else:
        position_ids = [position.get("position_id") for position in positions]
        position_units = [position.get("unit_id") for position in positions]
        if len(set(position_ids)) != 10 or len(set(position_units)) != 10:
            errors.append("Coherence position IDs and units must be unique")
        if any(unit_id not in units for unit_id in position_units):
            errors.append("A coherence position references an unknown unit")
        if any(position.get("anchor") != "unit_start" for position in positions):
            errors.append("Every coherence position must use the predeclared unit_start anchor")

    if not split_manifest.get("strategy_selection_rule"):
        errors.append("Strategy selection rule is missing")
    if split_manifest.get("freeze_stage") != "before any retrieval experiment":
        errors.append("Freeze stage must explicitly precede retrieval")

    expected_questions_hash = sha256(QUESTIONS_PATH)
    expected_corpus_hash = sha256(CORPUS_MANIFEST_PATH)
    if freeze and not errors:
        split_manifest["questions_sha256"] = expected_questions_hash
        split_manifest["corpus_manifest_sha256"] = expected_corpus_hash
        SPLIT_PATH.write_text(
            json.dumps(split_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    elif not freeze:
        if split_manifest.get("questions_sha256") != expected_questions_hash:
            errors.append("questions.json differs from its frozen SHA-256")
        if split_manifest.get("corpus_manifest_sha256") != expected_corpus_hash:
            errors.append("data/manifest.json differs from its frozen SHA-256")

    if errors:
        raise ValueError("Benchmark validation failed:\n- " + "\n- ".join(errors))
    return {
        "questions": len(questions),
        "dev": len(split_ids["dev"]),
        "test": len(split_ids["test"]),
        "filters": filter_count,
        "test_filters": test_filter_count,
        "evidence_verified": len(questions),
        "coherence_positions": len(positions),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--freeze", action="store_true",
        help="Write current questions/corpus SHA-256 values after all other checks pass.",
    )
    args = parser.parse_args()
    try:
        summary = validate(freeze=args.freeze)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
    mode = "frozen" if args.freeze else "validated"
    print(
        f"Benchmark {mode} OK: {summary['questions']} questions "
        f"({summary['dev']} Dev/{summary['test']} Test), "
        f"{summary['filters']} filters ({summary['test_filters']} Test), "
        f"{summary['evidence_verified']}/{summary['questions']} evidence verified, "
        f"{summary['coherence_positions']} coherence positions."
    )


if __name__ == "__main__":
    main()
