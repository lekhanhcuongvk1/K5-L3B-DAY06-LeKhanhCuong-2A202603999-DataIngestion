# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **Corpus Wikipedia tiếng Việt**

## Tổng quan bài nộp

Corpus **Điện toán và ngôn ngữ lập trình — Wikipedia
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

Benchmark tiếng Việt được khóa trước retrieval, gồm 20 câu từ 20 bài khác nhau: 15 Dev / 5
Test, 5 câu có `collection` filter (2 Test), 20/20 evidence được validator xác
minh và 10 vị trí coherence được chọn trước retrieval. Xem
[`benchmark/questions.json`](benchmark/questions.json) và
[`benchmark/split_manifest.json`](benchmark/split_manifest.json).

Pipeline xử lý đủ 30 đơn vị với 0 lỗi và tạo hai artifacts có truy vết: A fixed
500 ký tự/overlap 50 có 759 chunks; B paragraph-aware tối đa 1.000 ký tự/không
overlap có 418 chunks. Toàn bộ span, metadata, coverage và ID ổn định đã được
[`validate_cp2.py`](starter/scripts/validate_cp2.py) kiểm tra; chạy lại tạo
artifacts byte-identical.

Model được so sánh trên cùng B chunks và 15 Dev: MiniLM đạt Hit@1 `10/15`,
Evidence Hit@3 `12/15`; BKAI đạt Hit@1 `9/15`, Evidence Hit@3 `14/15`. Theo rule
ưu tiên Hit@3 đã khóa, BKAI được chọn cho A/B/C. Index chính thức nằm ở bảng
`day06_chunks_vi` với `vector(768)`, 759 hàng A và 418 hàng B; C dùng chung B và
chỉ thêm `collection` filter. Hai lượt upsert giữ nguyên count, 9 smoke traces
chỉ dùng Q01/Q04/Q10 thuộc Dev và Test chưa mở. Lần chạy chính thức đo được
159,373 giây tổng, trong đó embedding A+B là 152,737 giây; chi phí API 0 USD.
A/B/C được chạy trên Dev, freeze B rồi mới chạy Test đúng một lần. Kết quả:

| Strategy | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 | Coherence /2 |
|---|---:|---:|---:|---:|---:|
| A | 10/15 | 12/15 | 3/5 | 4/5 | 1,2 |
| B | 9/15 | **14/15** | 3/5 | 4/5 | **1,8** |
| C | 9/15 | **14/15** | 3/5 | 4/5 | **1,8** |

Metadata đúng 45/45 records; C tuân thủ filter 6/6 Test hits; grounding thủ
công đạt 2,0/2 cho cả ba strategy. Q18 vẫn được giữ là miss theo full-quote
metric dù top-3 có bằng chứng tương đương đủ trả lời. B được chọn trước Test vì
Hit@3/coherence cao hơn và index nhỏ hơn A; C không tăng metric vì `collection`
còn quá rộng. Xem [`strategy_comparison.md`](results/strategy_comparison.md).
Báo cáo cá nhân, cấu trúc nộp bài và toàn bộ artifacts đã được tái xác minh mà
không chạy lại Test. Báo cáo chính thức:
[`2A202603999_LeKhanhCuong.md`](report/individual/2A202603999_LeKhanhCuong.md).

## Setup, chạy và xác minh

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
python starter/scripts/validate_benchmark.py
python starter/scripts/prepare_chunks.py
python starter/scripts/validate_cp2.py
starter\.venv\Scripts\python starter\scripts\run_model_bakeoff.py
Push-Location starter
.\.venv\Scripts\python -m src.run
Pop-Location
starter\.venv\Scripts\python starter\scripts\validate_cp3.py
starter\.venv\Scripts\python starter\scripts\validate_cp4.py
python starter/scripts/validate_submission.py
$env:PYTHONPATH = (Resolve-Path '.\starter\.venv\Lib\site-packages').Path
python -m unittest discover -s tests -v
```

`src.run` tái tạo embedding/index và chỉ chạy smoke trên Dev. Kết quả Test chính
thức đã đóng băng; không gọi lại `run_benchmark.py --split test`. Người chấm có
thể xác minh artifacts hiện có bằng các validator mà không cần mở lại holdout.

Không chạy `download_vi_wikipedia.py --refresh` sau khi CP1 đã khóa benchmark,
vì revision và thành viên chuyên mục có thể thay đổi.

## Các bất biến thí nghiệm

- Benchmark mới phải có ít nhất 15 Dev / 5 Test và được chốt trước retrieval.
- Nếu so sánh model, chỉ dùng Dev trên cùng chunks/query; khóa một model trước
  đánh giá A/B/C chính thức.
- A–B chỉ thay chunking; B–C chỉ thay metadata filter `collection`.
- Test đã chạy đúng một lần sau freeze; `.test_completed` chặn chạy lại.
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
