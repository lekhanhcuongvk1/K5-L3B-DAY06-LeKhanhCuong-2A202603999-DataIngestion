# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

## Trạng thái triển khai của bài làm

CP0 sử dụng corpus **The Python Tutorial — Python 3.11.18 documentation** từ
Python Software Foundation. Corpus plain-text được lưu tại
`data/python_tutorial/`; `data/manifest.json` ghi nguồn, giấy phép, checksum,
ranh giới 68 đơn vị nội dung và số ký tự kiểm chứng được. `index.txt` và
`LICENSE.txt` được giữ để truy vết nhưng không tính vào quy mô corpus. Trường
metadata dùng cho filter là `chapter`, lấy trực tiếp từ ranh giới chương/file
chính thức (16 giá trị phân biệt).

Triển khai hoàn chỉnh sử dụng:

- embedding thật chạy local:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 chiều,
  cosine); không cần API key và không gửi corpus tới provider;
- vector store: PostgreSQL 16 + pgvector 0.8.7 bằng Docker, lưu bền vững trong
  named volume của Compose;
- Python 3.11; máy cần Docker, mạng cho lần tải image/dependency/model đầu,
  và nên có tối thiểu khoảng 4 GB RAM trống khi tải/chạy model.

Thiết lập trên Windows PowerShell:

```powershell
cd starter
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
.venv\Scripts\python scripts/check_setup.py
cd ..
starter\.venv\Scripts\python starter\scripts\build_manifest.py
```

Hai lệnh kiểm tra cuối phải lần lượt in `Setup OK` và `Manifest OK`. Script
manifest tái tính checksum, chuẩn hóa Unicode/whitespace và từ chối corpus có
dưới 30 đơn vị hoặc đơn vị ngắn hơn 1.500 ký tự. Không commit `.env`, `.venv`,
cache model hay dữ liệu PostgreSQL. Nguồn và điều khoản sử dụng chính thức:
[Python Tutorial](https://docs.python.org/3.11/tutorial/) và
[PSF License](https://docs.python.org/3.11/license.html).

## Chạy pipeline và kiểm tra kết quả

Các lệnh dưới đây chạy từ thư mục gốc repository. Model được tải từ Hugging
Face trong lần chạy đầu và được cache ngoài repository.

```powershell
# Kiểm tra corpus, benchmark và unit tests
starter\.venv\Scripts\python starter\scripts\build_manifest.py
starter\.venv\Scripts\python starter\scripts\validate_benchmark.py
starter\.venv\Scripts\python -m unittest discover -s tests -v

# Tái tạo chunks A/B và artifacts CP2
starter\.venv\Scripts\python starter\scripts\prepare_chunks.py

# Embedding thật, pgvector và Dev-only smoke test CP3
Push-Location starter
.\.venv\Scripts\python -m src.run
Pop-Location

# Xác minh artifacts CP4 đã được đóng băng
starter\.venv\Scripts\python starter\scripts\validate_cp4.py
```

`run_benchmark.py` được thiết kế theo ba stage `dev → freeze → test`. Test đã
được chạy đúng một lần và `results/.test_completed` ngăn chạy lại. Không chạy
lại stage Test hoặc chỉnh chiến lược theo kết quả Test hiện có.

## Cấu hình và kết quả chính

| Strategy | Chunking | Filter | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---|---|---:|---:|---:|---:|
| A | Fixed 500, overlap 50 | Không | 3/15 | 7/15 | 0/5 | 0/5 |
| B | Paragraph-aware, max 1.000 | Không | 7/15 | 9/15 | 1/5 | 2/5 |
| C | Giống B, dùng chung index | `chapter` khi khai báo | 7/15 | 9/15 | 1/5 | 3/5 |

Strategy **B** được chọn và freeze trên Dev trước khi xem Test. C đạt Test
Evidence Hit@3 cao hơn nhưng không được dùng để thay đổi lựa chọn. Embedding và
ingestion A+B mất 26,385 giây trong lần đo được lưu, chi phí API là 0 USD.

Artifacts quan trọng:

- corpus và quyền: [`data/manifest.json`](data/manifest.json);
- benchmark/split: [`benchmark/questions.json`](benchmark/questions.json) và
  [`benchmark/split_manifest.json`](benchmark/split_manifest.json);
- trace A/B/C Dev/Test: [`results/traces/`](results/traces/);
- metric: [`results/retrieval_metrics.csv`](results/retrieval_metrics.csv);
- manual audits: [`results/coherence_audit.csv`](results/coherence_audit.csv),
  [`results/metadata_audit.csv`](results/metadata_audit.csv),
  [`results/grounding_audit.csv`](results/grounding_audit.csv);
- freeze và phân tích: [`results/strategy_freeze.json`](results/strategy_freeze.json)
  và [`results/strategy_comparison.md`](results/strategy_comparison.md);
- báo cáo cá nhân:
  [`report/individual/2A202603999_LeKhanhCuong.md`](report/individual/2A202603999_LeKhanhCuong.md).

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Bài làm đã hoàn thiện pipeline trong [`starter/src/`](starter/src/) với PostgreSQL + pgvector. Xem [starter/README](starter/README.md) để dựng database và chạy lại.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
