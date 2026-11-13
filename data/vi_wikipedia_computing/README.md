# Corpus snapshot: điện toán trên Wikipedia tiếng Việt

Thư mục này chứa 30 bản plain-text được trích từ 30 bài độc lập trên
Wikipedia tiếng Việt vào ngày 2026-11-13. Mỗi nhóm nguồn có 15 bài:

- `Thể loại:Ngôn ngữ lập trình`;
- `Thể loại:Khoa học máy tính`.

Mỗi bài có ít nhất 1.500 ký tự sau chuẩn hóa. `source_catalog.json` ghi tiêu
đề, URL chính tắc, MediaWiki page ID, revision ID, thời điểm revision, nhóm
nguồn, checksum và đường dẫn local cho từng bài. `../manifest.json` là manifest
được pipeline sử dụng và kiểm tra.

Nội dung Wikipedia được cung cấp theo giấy phép
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Attribution
được thực hiện bằng tiêu đề, URL và revision ID; lịch sử người đóng góp có thể
truy cập từ URL của từng bài. Xem thêm
[Wikimedia Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use).

Tạo snapshot mới, chỉ trước khi xây benchmark:

```powershell
python starter/scripts/download_vi_wikipedia.py --refresh
python starter/scripts/build_manifest.py
```

Không dùng `--refresh` sau khi benchmark đã được chốt vì revision hoặc thành
viên chuyên mục có thể thay đổi.
