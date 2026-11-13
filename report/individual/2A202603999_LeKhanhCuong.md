# Báo cáo cá nhân — Day 6

**Học viên:** Lê Khánh Cường · **MSSV:** 2A202603999 · **Lớp:** L3B

## Dữ liệu và pipeline

- **Chủ đề và nguồn:** Python programming, sử dụng *The Python Tutorial — Python
  3.11.18 documentation* của Python Software Foundation. Nội dung và giấy phép
  PSF License Version 2 được lưu tại `data/python_tutorial/`; manifest ghi URL,
  version, checksum và copyright.
- **Quy mô và cách tính:** corpus plain-text không phân trang gồm 68 đơn vị liên
  tiếp, mỗi đơn vị tối thiểu 1.500 ký tự chuẩn hóa. Tổng cộng 231.959 ký tự; đơn
  vị ngắn nhất 2.108 và dài nhất 4.691 ký tự. `index.txt` và `LICENSE.txt` được
  giữ để truy vết nhưng không tính vào nội dung.
- **Chuẩn hóa:** Unicode NFC, newline LF, gom whitespace ngang và giữ ranh giới
  đoạn. Mọi unit/chunk giữ `source`, `unit_id` và character span. Lần xử lý cuối
  có 68/68 unit hợp lệ, 0 processing error. Corpus không phân trang nên `page`
  là `null`, không tạo số trang giả.
- **Embedding:** local Sentence Transformers 5.7.0, model
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 chiều,
  normalized embeddings, batch 32, CPU; query/document dùng cùng model và cách
  xử lý. Model đa ngôn ngữ phù hợp query tiếng Việt và corpus tiếng Anh.
- **Vector store:** PostgreSQL 16.16 + pgvector 0.8.7, bảng persistent
  `day06_chunks`, exact cosine search bằng `<=>`, không approximate index.
  Re-ingestion giữ counts A=543/B=289 và stale cleanup đã được test.
- **Thời gian/chi phí:** model load 5,983 giây; embedding A+B 19,166 giây; hai
  lượt upsert A+B 0,818 giây; tổng lần đo 26,385 giây. API cost: 0 USD.
- **Metadata:** `document_id`, `source`, `page`, `unit_id`, `chapter`, `version`,
  `sequence_in_chapter`, `char_start`, `char_end`. `chapter` lấy từ ranh giới
  file/chương chính thức và dùng để lọc khi câu hỏi khai báo chương.

Lệnh chính:

```powershell
cd starter
.\.venv\Scripts\python -m src.run
cd ..
starter\.venv\Scripts\python starter\scripts\validate_cp4.py
```

## Cấu hình và benchmark

- **A:** fixed-size 500 ký tự, overlap 50; 543 chunks; dense cosine, không filter.
- **B:** paragraph-aware, tối đa 1.000 ký tự, không overlap; 289 chunks; dense
  cosine, không filter.
- **C:** dùng chính chunks/vector/index B; chỉ áp dụng `chapter` filter khi câu
  hỏi đã khai báo filter. Vì vậy B–C chỉ khác filter.
- Benchmark có 20 câu viết trước retrieval: 15 Dev và 5 Test; gồm direct,
  paraphrase, conditional và metadata-disambiguation. Có 4 câu filter, 2 câu
  thuộc Test. Validator xác minh 20/20 evidence nằm trong đúng source/unit.
- Trước Test, quy tắc chọn là ưu tiên Dev Evidence Hit@3, sau đó coherence, rồi
  chi phí/storage/độ phức tạp. B được freeze lúc
  `2026-11-13T21:04:12+07:00`; Test được chạy đúng một lần sau đó.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Mean retrieval | Chi phí |
|---|---|---:|---:|---:|---:|---:|
| A | Dev | 3/15 | 7/15 | 543 | 43,033 ms | 0 USD |
| A | Test | 0/5 | 0/5 | 543 | 33,210 ms | 0 USD |
| B | Dev | 7/15 | 9/15 | 289 | 32,862 ms | 0 USD |
| B | Test | 1/5 | 2/5 | 289 | 32,809 ms | 0 USD |
| C | Dev | 7/15 | 9/15 | 289 dùng chung B | 27,754 ms | 0 USD |
| C | Test | 1/5 | 3/5 | 289 dùng chung B | 29,706 ms | 0 USD |

Retrieval time là wall-clock trên máy thực nghiệm, không phải benchmark hiệu
năng có kiểm soát. C không có chi phí embedding/ingestion riêng vì dùng chung B.

| Strategy | Coherence /2 (n) | Metadata đủ và đúng | Filter tuân thủ | Grounding 0/1/2 và mean /2 |
|---|---:|---:|---:|---:|
| A | 1,0 (10) | 15/15 | N/A | 1/2/2; mean 1,2 |
| B | 2,0 (10) | 15/15 | N/A | 2/1/2; mean 1,0 |
| C | 2,0 (10) | 15/15 | 6/6 returned filtered hits | 1/1/3; mean 1,4 |

Toàn bộ metadata audit đạt 45/45 bản ghi. Nhãn coherence và grounding được Codex
review thủ công với rationale; học viên cần xác nhận lại trước khi nộp. Đây là
đánh giá evidence retrieval, không phải LLM answer accuracy.

Artifacts:

- traces: `results/traces/dev_A.jsonl` … `results/traces/test_C.jsonl`;
- metrics: `results/retrieval_metrics.csv`;
- labels: `results/coherence_audit.csv`, `results/metadata_audit.csv`,
  `results/grounding_audit.csv`;
- freeze: `results/strategy_freeze.json` và `results/.test_completed`;
- cấu hình: `artifacts/experiment_log.csv`, `results/run_metadata.json`.

## Phân tích và kết luận

### So sánh A–B

B tăng Dev Evidence Hit@3 từ 7/15 lên 9/15 và coherence từ 1,0 lên 2,0,
đồng thời giảm số chunks từ 543 xuống 289. Các fixed window A thường kết thúc
giữa câu hoặc giữa token, làm mất full evidence. B được chọn theo quy tắc Dev đã
định trước.

### So sánh B–C

B/C giống hoàn toàn về chunks, vectors, model, store và metric. Với câu không
filter, top-3 của B/C giống nhau. Trên Test, filter của C đưa full evidence Q18
vào rank 3, nâng Evidence Hit@3 từ 2/5 lên 3/5. Đây là phân tích sau freeze;
không dùng kết quả này để thay đổi strategy đã chọn.

### Ví dụ lỗi

1. **Q04, `datastructures.txt`, unit `py311-05-u02`:** cả A/B/C đều không lấy
   được evidence `collections.deque`; kết quả bị nhiễu bởi các đoạn nói chung về
   alternatives/performance. Đây là failure semantic retrieval xuyên ngôn ngữ.
2. **Q14, `inputoutput.txt`, unit `py311-07-u04`:** retrieval lấy evidence tương
   đương về file tự đóng từ chương Errors, nhưng chunk thiếu chủ thể `with` và
   không trúng frozen gold unit/full quote. Official Evidence Hit@3 là false và
   grounding chỉ 1/2.
3. **Q18, `floatingpoint.txt`, unit `py311-15-u02`:** B bỏ lỡ khuyến nghị đầy đủ
   về `decimal`; C tìm được ở rank 3 nhờ chapter filter. A lấy các fragment bị
   chia ở fixed boundary, cho thấy full-evidence metric và grounding có thể khác.

### Kết luận và hạn chế

Chọn **B** vì đạt Dev retrieval cao nhất, coherence tốt, ít chunks hơn A và đơn
giản hơn C khi các chỉ số Dev hòa. C hữu ích khi context cung cấp chapter đáng
tin, nhưng filter sai/thiếu có thể loại evidence đúng.

Test chỉ có 5 câu; corpus chỉ có một tài liệu; model và runtime chỉ được đo trên
một máy. Nhãn có một reviewer AI-assisted và có nguy cơ chủ quan. Kết quả không
chứng minh B tốt nhất cho corpus khác. Không có Test-dependent tuning hay rerun.

Nếu mở rộng, tôi sẽ phân tích lỗi trên Dev, thử reranking hoặc embedding mạnh hơn,
sau đó tạo holdout mới chưa từng xem. Bộ Test hiện tại đã được mở nên không thể
dùng tiếp như một đánh giá độc lập cho cấu hình mới.
