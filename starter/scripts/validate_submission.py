"""Final submission/readiness checks for the Day 06 repository."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "report" / "individual" / "2A202603999_LeKhanhCuong.md"
REQUIRED_PATHS = [
    "STUDENT.md", "README.md", "data/manifest.json", "benchmark/questions.json",
    "benchmark/split_manifest.json", "artifacts/experiment_log.csv",
    "results/run_metadata.json", "results/retrieval_metrics.csv",
    "results/strategy_freeze.json", "results/.test_completed",
    "results/coherence_audit.csv", "results/metadata_audit.csv",
    "results/grounding_audit.csv", "results/strategy_comparison.md",
    "report/individual/2A202603999_LeKhanhCuong.md",
]


def fail(message: str) -> None:
    raise ValueError(message)


def validate_links(markdown_path: Path) -> None:
    text = markdown_path.read_text(encoding="utf-8")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#")):
            continue
        clean = target.split("#", 1)[0]
        resolved = (markdown_path.parent / clean).resolve()
        if not resolved.exists():
            fail(f"Broken local link in {markdown_path.relative_to(ROOT)}: {target}")


def main() -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).exists()]
    if missing:
        fail(f"Missing required submission paths: {missing}")

    student = (ROOT / "STUDENT.md").read_text(encoding="utf-8")
    for expected in (
        "Lê Khánh Cường", "2A202603999", "L3B",
        "Điện toán và ngôn ngữ lập trình", "Wikipedia tiếng Việt",
    ):
        if expected not in student:
            fail(f"STUDENT.md is missing {expected!r}")
    if "Họ và tên:\n" in student or "MSSV:\n" in student:
        fail("STUDENT.md still has blank identity fields")

    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    if manifest["summary"]["content_unit_count"] < 30:
        fail("Corpus has fewer than 30 valid units")
    benchmark = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))
    if len(benchmark["questions"]) < 20:
        fail("Benchmark has fewer than 20 questions")

    metrics = {}
    with (ROOT / "results" / "retrieval_metrics.csv").open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            metrics[(row["strategy"], row["split"])] = row
    if len(metrics) != 6:
        fail("Expected six strategy/split metric rows")
    report = REPORT.read_text(encoding="utf-8")
    for (strategy, split), row in metrics.items():
        hit1 = f"{row['hit_at_1_n']}/{row['hit_at_1_N']}"
        hit3 = f"{row['evidence_hit_at_3_n']}/{row['evidence_hit_at_3_N']}"
        if not re.search(rf"\| {strategy} \| {split.title()} \| {re.escape(hit1)} \| {re.escape(hit3)} \|", report):
            fail(f"Report metric mismatch for {strategy}/{split}")
    for forbidden in (
        "Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:",
        "A / B / C (tham số cụ thể",
        "So sánh A–B và B–C; 2 ví dụ sai",
    ):
        if forbidden in report:
            fail(f"Report still contains template placeholder: {forbidden}")
    if report.count("**Q") < 3:
        fail("Report must contain at least two concrete failure examples")

    with (ROOT / "artifacts" / "experiment_log.csv").open(encoding="utf-8", newline="") as source:
        experiments = list(csv.DictReader(source))
    if len(experiments) != 3 or {row["strategy"] for row in experiments} != {"A", "B", "C"}:
        fail("Experiment log does not contain complete A/B/C rows")
    if any(
        not row["dev_evidence_hit_at_3"] or not row["test_evidence_hit_at_3"]
        for row in experiments
    ):
        fail("Experiment log contains blank measured metrics")

    for split, count in (("dev", 15), ("test", 5)):
        for strategy in "ABC":
            path = ROOT / "results" / "traces" / f"{split}_{strategy}.jsonl"
            if len(path.read_text(encoding="utf-8").splitlines()) != count:
                fail(f"Trace count mismatch: {path.relative_to(ROOT)}")

    validate_links(ROOT / "README.md")
    validate_links(ROOT / "starter" / "README.md")
    validate_links(ROOT / "benchmark" / "README.md")
    validate_links(REPORT)

    source_todos = subprocess.run(
        ["rg", "-n", "TODO|NotImplementedError", "starter/src"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    if source_todos.returncode == 0:
        fail("Unresolved implementation placeholder in starter/src:\n" + source_todos.stdout)
    if source_todos.returncode not in (0, 1):
        fail("Unable to scan implementation placeholders")

    print(
        "Submission validation OK: required files, 30 units, 20 questions, "
        "6 metric rows, A/B/C experiment log, traces, report values, and local links."
    )


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(f"Submission validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
