# Báo cáo cá nhân — Day 6

**Học viên:** Lê Khánh Cường — **MSSV:** 2A202603999 — **Lớp:** L3B

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số đơn vị:** corpus gồm 30 bài độc lập về điện toán và ngôn ngữ lập trình từ Wikipedia tiếng Việt, snapshot ngày 2026-11-13. Mỗi bài được tính là một đơn vị nội dung khi có ít nhất 1.500 ký tự sau chuẩn hóa; không nhân bản bài để đủ số lượng. Tổng cộng 30/30 đơn vị hợp lệ và 334.955 ký tự. Nội dung và attribution được phân phối theo CC BY-SA 4.0. URL chuẩn, page ID, revision ID, thời điểm truy cập, checksum và số ký tự của từng bài nằm trong [manifest](../../data/manifest.json) và [source catalog](../../data/vi_wikipedia_computing/source_catalog.json).
- **Chuẩn hóa, lỗi và giới hạn:** pipeline đọc UTF-8, chuẩn hóa Unicode NFC, newline và khoảng trắng nhưng giữ ranh giới đoạn; mỗi chunk giữ span ký tự để truy ngược. Cả 30 bài được xử lý, không có trang rỗng/lỗi; log nằm tại [processing_errors.jsonl](../../results/processing_errors.jsonl). Corpus chỉ có hai chuyên mục rộng, văn phong và độ dài bài không đồng đều; snapshot không đại diện cho toàn bộ tiếng Việt hay mọi miền tri thức.
- **Embedding và lưu trữ:** model local Sentence Transformers `bkai-foundation-models/vietnamese-bi-encoder`, revision `84f9d9ada0d1a3c37557398b9ae9fcedcdf40be0`, Apache-2.0, 768 chiều, CPU, batch 32, vector được chuẩn hóa; query và document dùng cùng cách xử lý. Phiên bản: sentence-transformers 5.7.0, transformers 5.22.2, torch 2.15.0. Store là PostgreSQL 16 + pgvector 0.8.7, bảng `day06_chunks_vi`, cosine exact search, lưu bền vững. Lần chạy chính thức mất 159,373 giây (embedding A+B: 152,737 giây; hai lượt upsert: 1,792 giây), chi phí API **0 USD**. Hai lượt upsert giữ nguyên A=759 và B=418, chứng minh idempotence. C dùng chung vector/index B.
- **Metadata:** mỗi chunk có `document_id`, `source`, `page` (null vì nguồn text không phân trang), `unit_id`, `title`, `canonical_url`, `version`, `sequence_in_source`, `char_start`, `char_end` và `collection`. `collection` là chuỗi lấy trực tiếp từ chuyên mục MediaWiki (`ngon_ngu_lap_trinh` hoặc `khoa_hoc_may_tinh`), dùng làm filter cho C; không suy đoán từ nội dung. Trường này hữu ích để loại collection ngoài phạm vi nhưng độ phân giải còn thô.

Lệnh tái lập chính (từ root; không chạy lại Test đã đóng băng):

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
Push-Location starter
.\.venv\Scripts\python -m src.run
Pop-Location
starter\.venv\Scripts\python starter\scripts\validate_cp3.py
starter\.venv\Scripts\python starter\scripts\validate_cp4.py
python starter/scripts/validate_submission.py
```

## Cấu hình và benchmark

- **A:** cửa sổ cố định 500 ký tự, overlap 50, không filter; 759 chunks.
- **B:** theo ranh giới đoạn, tối đa 1.000 ký tự, overlap 0, không filter; 418 chunks. A–B chỉ thay chunking.
- **C:** dùng byte-identical chunks, vector và index của B; chỉ thêm `collection` filter khi câu hỏi cung cấp trước phạm vi hợp lệ. B–C chỉ thay filter, C không phát sinh embedding riêng.
- Benchmark `vi-wikipedia-computing-gold-v1` có 20 câu từ 20 bài khác nhau, khóa trước retrieval: 15 Dev / 5 Test. Có 5 câu filter (Q04, Q10, Q14 Dev; Q16, Q18 Test), 20/20 evidence được đối chiếu trực tiếp với source sau chuẩn hóa. Không đưa answer, gold source, unit ID hay evidence vào query/filter. Checksum câu hỏi là `235c97d0a3db97f5a805a1d0a77351f78f0cdbef19363cbc00e35162f1f46305`.
- Quy tắc chọn đã khóa trước Test: tối đa Dev Evidence Hit@3; nếu hòa, ưu tiên coherence trung bình; tiếp theo là thời gian, chunk count và độ phức tạp vận hành. Theo quy tắc này, thứ tự freeze là B > C > A. Test được chạy đúng một lần sau freeze; marker ngăn chạy lại nằm tại `results/.test_completed`.

## Kết quả

Thời gian dưới đây là mean retrieval/query; embedding A+B được đo chung 152,737 giây nên không cộng lặp vào từng hàng. Tất cả cấu hình có chi phí API 0 USD.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---:|---:|---:|
| A | Dev | 10/15 | 12/15 | 759 | 38,509 ms | 0 USD |
| A | Test | 3/5 | 4/5 | 759 | 34,597 ms | 0 USD |
| B | Dev | 9/15 | 14/15 | 418 | 29,033 ms | 0 USD |
| B | Test | 3/5 | 4/5 | 418 | 30,808 ms | 0 USD |
| C | Dev | 9/15 | 14/15 | 418 (dùng chung B) | 29,224 ms | 0 USD |
| C | Test | 3/5 | 4/5 | 418 (dùng chung B) | 27,163 ms | 0 USD |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ | Grounding 0/1/2 (số câu), trung bình /2 |
|---|---:|---:|---:|---:|
| A | 1,2 (10) | 15/15 | N/A | 0/0/5, 2,0/2 |
| B | 1,8 (10) | 15/15 | N/A | 0/0/5, 2,0/2 |
| C | 1,8 (10) | 15/15 | 6/6 top-3 records của 2 câu Test có filter | 0/0/5, 2,0/2 |

Tổng metadata là 45/45 top-3 Test records đầy đủ và đúng. Coherence dùng cùng 10 vị trí nguồn đã chọn trước retrieval. Grounding đọc toàn bộ top-3 của cùng 5 câu Test cho từng strategy, chấm độ đủ của evidence retrieval (không phải độ chính xác câu trả lời LLM). Trace: [Dev A](../../results/traces/dev_A.jsonl), [Dev B](../../results/traces/dev_B.jsonl), [Dev C](../../results/traces/dev_C.jsonl), [Test A](../../results/traces/test_A.jsonl), [Test B](../../results/traces/test_B.jsonl), [Test C](../../results/traces/test_C.jsonl). Nhãn và lý do: [coherence](../../results/coherence_audit.csv), [metadata](../../results/metadata_audit.csv), [grounding](../../results/grounding_audit.csv). Codex hỗ trợ tạo code, phân tích và gán nhãn audit; metadata được kiểm tra cơ học với chunks, còn coherence/grounding được đọc thủ công. Đây là một reviewer hỗ trợ bằng AI nên có nguy cơ thiên lệch; tác giả chịu trách nhiệm đọc, hiểu và xác nhận các nhãn trước khi nộp.

## Phân tích và kết luận

- **A–B:** B tăng Dev Evidence Hit@3 từ 12/15 lên 14/15 và coherence từ 1,2 lên 1,8; giảm 341 chunks (44,9%) và mean Dev retrieval từ 38,509 xuống 29,033 ms. Đổi lại, Dev Hit@1 giảm 10/15 xuống 9/15. Test A/B bằng nhau trên chỉ 5 câu nên không đủ để tuyên bố B tốt hơn tổng quát.
- **B–C:** chunks/vector/model/store giống nhau; C chỉ lọc collection. C tuân thủ 6/6 returned records ở hai câu Test có filter nhưng Hit@1/Hit@3 không đổi, vì nhiễu quan trọng vẫn nằm trong đúng collection. Chênh lệch latency vài ms không nên diễn giải mạnh trên một lần đo nhỏ.
- **Q10 — nguồn gold “Hình học tính toán”:** A/B/C đều trả các đoạn tổng quan từ “Khoa học máy tính” trong top-3. Hai bài cùng collection `khoa_hoc_may_tinh`, nên filter thô không loại được nhiễu.
- **Q18 — nguồn gold “AlphaFold”:** B/C xếp bài AlphaFold rank 1, A xếp “Cơn sốt AI” rank 1. Top-3 có bằng chứng tương đương đủ trả lời về dự đoán cấu trúc protein từ trình tự amino acid, nên grounding là 2; tuy nhiên không chunk nào chứa trọn gold quote đã khai báo, vì vậy Evidence Hit@3 chính thức vẫn là miss. **Q14** trên Dev cũng cho thấy A cắt thiếu full evidence VAE, trong khi B/C giữ đủ ở rank 2.
- **Chọn B:** phù hợp corpus này vì ưu tiên recall top-3 và coherence, index nhỏ, truy xuất nhanh hơn và không phụ thuộc filter do người dùng cung cấp. C chỉ nên dùng khi collection đầu vào đáng tin; filter sai hoặc quá rộng có thể không giúp, còn filter sai phạm vi có thể loại evidence đúng.
- **Giới hạn:** corpus chỉ 30 bài và hai collection; Test có 5 câu; nhãn thủ công do một reviewer hỗ trợ bằng AI; timing chạy local CPU/pgvector và không có lặp thống kê; chi phí 0 USD không phản ánh điện năng/phần cứng. Không dùng kết quả Test để sửa model, chunks, filter hoặc ranking và không suy rộng ngoài corpus.
- **Nếu mở rộng:** tạo holdout mới lớn hơn trước mọi tuning, thêm metadata mục/tiểu mục có nguồn xác thực, lặp phép đo latency, có reviewer độc lập, và thử hybrid dense+BM25 hoặc reranker trên Dev. Các mở rộng phải giữ Test hiện tại bất biến hoặc công bố đây không còn là holdout độc lập.

