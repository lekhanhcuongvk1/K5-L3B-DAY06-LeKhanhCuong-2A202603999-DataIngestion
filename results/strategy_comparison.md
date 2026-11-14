# CP4 strategy comparison — corpus tiếng Việt

## Integrity và cấu hình

Benchmark gồm 15 Dev và 5 Test đã được checksum trước retrieval. Model BKAI
được chọn bằng Dev-only bake-off; ba strategy chính thức dùng cùng corpus,
model 768 chiều, PostgreSQL/pgvector, exact cosine và top-3. Strategy B được
chọn và freeze trước Test theo thứ tự `B > C > A`. Test chỉ chạy một lần.

- A: fixed 500 ký tự, overlap 50, 759 chunks, không filter.
- B: paragraph-aware tối đa 1.000 ký tự, không overlap, 418 chunks, không filter.
- C: dùng nguyên index/vector B; chỉ thêm `collection` filter khi câu hỏi cung
  cấp phạm vi. C không có chi phí embedding/ingestion riêng.

## Retrieval

| Strategy | Split | Hit@1 | Evidence Hit@3 | Mean retrieval |
|---|---|---|---|---:|
| A | Dev | 10/15 | 12/15 | 38,509 ms |
| A | Test | 3/5 | 4/5 | 34,597 ms |
| B | Dev | 9/15 | 14/15 | 29,033 ms |
| B | Test | 3/5 | 4/5 | 30,808 ms |
| C | Dev | 9/15 | 14/15 | 29,224 ms |
| C | Test | 3/5 | 4/5 | 27,163 ms |

## Bốn khía cạnh audit bổ sung

| Strategy | Coherence /2 (n=10) | Metadata đúng | Filter compliance | Grounding /2 (n=5) |
|---|---:|---:|---:|---:|
| A | 1,2 | 15/15 Test hits | N/A | 2,0 |
| B | 1,8 | 15/15 Test hits | N/A | 2,0 |
| C | 1,8 | 15/15 Test hits | 6/6 returned filtered hits | 2,0 |

Metadata đầy đủ và đúng ở 45/45 top-3 records. `collection` xuất phát trực tiếp
từ chuyên mục MediaWiki và hữu ích để loại toàn bộ collection ngoài phạm vi,
nhưng hai collection hiện tại còn rộng nên filter không cải thiện metric. Nhãn
grounding chấm độ đủ của evidence retrieval, không phải độ chính xác câu trả lời
LLM. Q18 có evidence tương đương đủ trả lời nên grounding là 2, dù full-quote
Evidence Hit@3 chính thức vẫn là false.

## Tác động chiến lược

### A–B: chỉ thay chunking

B tăng Dev Evidence Hit@3 từ 12/15 lên 14/15, tăng coherence từ 1,2 lên 1,8,
giảm số chunk 759 xuống 418 và giảm mean Dev retrieval từ 38,509 ms xuống
29,033 ms. Đổi lại, Dev Hit@1 giảm từ 10/15 xuống 9/15. Kết quả Test của A/B
bằng nhau trên mẫu 5 câu, nên không đủ bằng chứng để khẳng định B luôn tốt hơn;
B được chọn trước Test vì ưu tiên Dev Hit@3, sau đó coherence và tài nguyên.

### B–C: chỉ thay filter

B/C giống hoàn toàn về chunks, vectors, model, store và metric. Với câu không
filter, ranking giống nhau. Năm câu benchmark có filter, trong đó hai câu Test;
toàn bộ 6 top-3 Test records của C tuân thủ collection. Tuy nhiên filter không
đổi Hit@1/Hit@3 vì các ứng viên gây nhiễu của Q10 và Q18 cũng thuộc đúng
collection. Đây là giới hạn thực tế của metadata có độ phân giải thô.

## Failure cases

1. **Q10 — Hình học tính toán:** cả A/B/C không đưa bài gold vào top-3; ba vị
   trí đầu đều từ bài tổng quan `Khoa học máy tính`. Collection filter không thể
   phân biệt hai bài vì cả hai cùng `khoa_hoc_may_tinh`.
2. **Q18 — AlphaFold:** A xếp một đoạn `Cơn sốt AI` ở rank 1; B/C đưa bài
   `AlphaFold` lên rank 1. Các top-3 chứa bằng chứng tương đương “dự đoán cấu
   trúc protein chỉ từ trình tự amino acid”, nhưng không chứa trọn gold quote đã
   khai báo trong một chunk, nên metric full-evidence giữ nguyên miss.
3. **Q14 trên Dev:** A tìm đúng bài VAE ở rank 3 nhưng chunk bị cắt và thiếu
   full evidence; B/C giữ đoạn đầy đủ ở rank 2, minh họa lợi ích của chunking.

## Kết luận và giới hạn

Chọn B cho corpus này: recall top-3 và coherence tốt hơn, index nhỏ hơn, không
phụ thuộc filter do người dùng cung cấp. C phù hợp khi ngữ cảnh collection đáng
tin, nhưng filter sai hoặc quá rộng có thể không giúp hoặc loại evidence đúng.
Test chỉ có 5 câu; coherence/grounding do một reviewer hỗ trợ bởi Codex và cần
tác giả xác nhận. Không dùng Test để sửa model, chunks, filter hay ranking sau
khi freeze.
