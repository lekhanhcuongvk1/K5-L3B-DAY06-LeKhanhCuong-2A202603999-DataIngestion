"""Materialize manually reviewed coherence labels for the ten frozen positions."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# Labels were assigned by reading the complete chunk at each frozen unit_start.
# 0 = cut/unintelligible, 1 = understandable but context/idea is cut,
# 2 = self-contained and keeps a complete idea.
LABELS = {
    "A": {
        "C01": (1, "Định nghĩa chính đầy đủ nhưng chunk kết thúc giữa câu mô tả tín hiệu thay thế."),
        "C02": (1, "Định nghĩa callback đầy đủ nhưng phần phân biệt đồng bộ/bất đồng bộ bị cắt giữa câu."),
        "C03": (1, "Nguồn gốc Ada đầy đủ nhưng mô tả yêu cầu hệ nhúng bị cắt giữa câu."),
        "C04": (2, "Đoạn giới thiệu APL và kiểu mảng đa chiều trọn ý; phần sau chỉ bắt đầu mục tham khảo."),
        "C05": (1, "Mục đích AWK đầy đủ nhưng diễn giải lịch sử bị cắt giữa câu."),
        "C06": (1, "Định nghĩa đa xử lý bị cắt trong phần liệt kê cách xác định CPU."),
        "C07": (2, "Định nghĩa và ứng dụng hình học tính toán trọn ý trước heading tiếp theo."),
        "C08": (1, "Giới thiệu AlexNet đầy đủ nhưng đoạn về nhóm phát triển bị cắt giữa câu."),
        "C09": (1, "Định nghĩa VAE đầy đủ nhưng phần khác biệt kiến trúc bị cắt giữa câu."),
        "C10": (1, "Định nghĩa cơ chế chú ý bị cắt trước khi hoàn tất câu so sánh với chú ý con người."),
    },
    "B": {
        "C01": (2, "Các đoạn giới thiệu và mục đích Hello World kết thúc trọn câu, tự hiểu được."),
        "C02": (2, "Định nghĩa và phân biệt callback đồng bộ/bất đồng bộ được giữ trọn đoạn."),
        "C03": (2, "Nguồn gốc, nhu cầu hệ nhúng và yêu cầu thiết kế Ada đều trọn ý."),
        "C04": (2, "Đoạn giới thiệu APL trọn ý; thông tin tham khảo đi kèm không làm mất ngữ cảnh."),
        "C05": (1, "Lịch sử AWK trọn ý nhưng chunk kết thúc ngay sau lời dẫn cú pháp, chưa có cú pháp."),
        "C06": (2, "Định nghĩa đa xử lý và các cách hiểu CPU nằm trong một đoạn hoàn chỉnh."),
        "C07": (2, "Định nghĩa, ứng dụng và công thức vector đều kết thúc trọn câu."),
        "C08": (2, "Giới thiệu và thông tin nhóm phát triển AlexNet được giữ thành các đoạn hoàn chỉnh."),
        "C09": (1, "Giải thích VAE trọn ý nhưng chunk kết thúc bằng heading Kiến trúc chưa có nội dung."),
        "C10": (2, "Định nghĩa cơ chế chú ý là một đoạn hoàn chỉnh, tự hiểu được."),
    },
}


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> None:
    split = json.loads((ROOT / "benchmark" / "split_manifest.json").read_text(encoding="utf-8"))
    positions = {row["position_id"]: row for row in split["coherence_positions"]}
    chunks = {
        strategy: read_jsonl(ROOT / "results" / f"chunks_{strategy}.jsonl")
        for strategy in ("A", "B")
    }
    rows = []
    for strategy in ("A", "B", "C"):
        stored = "B" if strategy == "C" else strategy
        for position_id, position in positions.items():
            candidates = [
                row for row in chunks[stored]
                if row["unit_id"] == position["unit_id"] and row["char_start"] == 0
            ]
            if len(candidates) != 1:
                raise SystemExit(f"Expected one {stored} chunk for {position_id}, got {len(candidates)}")
            chunk = candidates[0]
            score, rationale = LABELS[stored][position_id]
            rows.append({
                "position_id": position_id,
                "unit_id": position["unit_id"],
                "anchor": position["anchor"],
                "strategy": strategy,
                "stored_strategy": stored,
                "chunk_id": chunk["chunk_id"],
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
                "score_0_2": score,
                "rationale": rationale,
                "review_method": "Manual review by Codex; author confirmation recommended",
            })
    path = ROOT / "results" / "coherence_audit.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    means = {
        strategy: sum(row["score_0_2"] for row in rows if row["strategy"] == strategy) / 10
        for strategy in ("A", "B", "C")
    }
    print(f"Coherence audit OK: 10 shared positions x 3 strategies; means={means}")


if __name__ == "__main__":
    main()
