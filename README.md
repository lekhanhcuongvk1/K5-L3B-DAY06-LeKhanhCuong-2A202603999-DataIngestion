# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **Nhánh thử nghiệm corpus tiếng Việt**

## Trạng thái triển khai

CP0 đã hoàn thành cho corpus **Điện toán và ngôn ngữ lập trình — Wikipedia
tiếng Việt**. Snapshot gồm 30 bài độc lập, 334.955 ký tự chuẩn hóa, chia đều
giữa hai chuyên mục nguồn `Ngôn ngữ lập trình` và `Khoa học máy tính`. Mỗi bài
có ít nhất 1.500 ký tự và giữ URL, page ID, revision ID, checksum cùng
attribution trong [`data/manifest.json`](data/manifest.json) và
[`source_catalog.json`](data/vi_wikipedia_computing/source_catalog.json).

Corpus được cung cấp theo
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Xem hướng dẫn
nguồn và tái tạo snapshot tại
[`data/vi_wikipedia_computing/README.md`](data/vi_wikipedia_computing/README.md).

Model ứng viên chính là
[`bkai-foundation-models/vietnamese-bi-encoder`](https://huggingface.co/bkai-foundation-models/vietnamese-bi-encoder)
(revision `84f9d9ada0d1a3c37557398b9ae9fcedcdf40be0`, Apache-2.0, 768 chiều dự
kiến, chạy local CPU, chi phí API 0 USD). Chính sách so sánh model và bảo vệ
holdout được khóa trong
[`artifacts/vietnamese_experiment_plan.json`](artifacts/vietnamese_experiment_plan.json).

CP1–CP5 của thí nghiệm tiếng Việt chưa chạy. Benchmark và kết quả tiếng Anh cũ
được giữ trong lịch sử Git tại commit `7c311d6`, không được trình bày như kết
quả của corpus mới.

## Xác minh CP0

Yêu cầu: Python 3.11, Docker và mạng cho lần lấy corpus/model đầu tiên.

```powershell
cd starter
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
.venv\Scripts\python scripts/check_setup.py
cd ..

python starter/scripts/build_manifest.py
$env:PYTHONPATH = (Resolve-Path '.\starter\.venv\Lib\site-packages').Path
python -m unittest discover -s tests -v
```

Không chạy `download_vi_wikipedia.py --refresh` sau khi CP1 đã khóa benchmark,
vì revision và thành viên chuyên mục có thể thay đổi.

## Các bất biến thí nghiệm

- Benchmark mới phải có ít nhất 15 Dev / 5 Test và được chốt trước retrieval.
- Nếu so sánh model, chỉ dùng Dev trên cùng chunks/query; khóa một model trước
  đánh giá A/B/C chính thức.
- A–B chỉ thay chunking; B–C chỉ thay metadata filter `collection`.
- Test chỉ chạy một lần sau khi model, strategy, benchmark và code đã freeze.
- Không dùng API key; không fallback sang mock/random vector.

## Tài liệu quy định

| Nội dung | Tài liệu |
|---|---|
| Quy trình và cách tính | [GUIDE.md](GUIDE.md) |
| Checkpoint | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Benchmark | [BENCHMARK.md](BENCHMARK.md) |
| Rubric | [RUBRIC.md](RUBRIC.md) |
| Quy tắc | [RULES.md](RULES.md) |
| Cấu trúc nộp bài | [SUBMISSION.md](SUBMISSION.md) |
| Mẫu báo cáo | [REPORT_TEMPLATE.md](REPORT_TEMPLATE.md) |

Không bắt buộc xây chatbot hoặc giao diện; trọng tâm là ingestion, retrieval,
đánh giá có kiểm soát và khả năng tái lập.
