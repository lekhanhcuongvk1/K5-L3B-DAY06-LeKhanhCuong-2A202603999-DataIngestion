# Benchmark tiếng Việt

Benchmark `vi-wikipedia-computing-gold-v1` gồm 20 câu hỏi tiếng Việt từ 20 bài
khác nhau trong snapshot corpus đã khóa: 15 Dev và 5 Test. Câu hỏi, expected
answer, source/unit và evidence được viết và kiểm chứng trước khi chạy retrieval.

- Dev được phép dùng để so sánh model và chiến lược.
- Test chỉ được mở một lần sau khi model và strategy đã freeze.
- Năm câu có filter `collection`: Q04, Q10, Q14, Q16 và Q18; trong đó Q16 và
  Q18 thuộc Test. Filter chỉ được dùng vì phạm vi được nêu ngay trong câu hỏi.
- Không đưa expected answer, source ID, unit ID hoặc evidence vào query.
- Evidence Hit chỉ được tính khi chunk đúng source/unit và chứa đủ evidence hoặc
  bằng chứng tương đương đã được kiểm chứng.

Kiểm tra và khóa checksum:

```powershell
python starter/scripts/validate_benchmark.py --freeze
python starter/scripts/validate_benchmark.py
```

Không sửa `questions.json`, `data/manifest.json` hoặc split sau bước freeze mà
không công khai việc invalidation và tạo holdout mới.
