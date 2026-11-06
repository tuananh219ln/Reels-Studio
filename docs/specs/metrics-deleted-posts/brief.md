# Số liệu của bài đã xóa: không tính vào tổng, không nuôi trung vị

## Vấn đề

4 video trên page Ăn Lành Sống Khỏe đăng qua API ngày 3–5/11/2026 bị ẩn với
người xem khác (lỗi phân phối, đã xác nhận: đăng tay cùng nội dung thì hiện).
Mốc 48h của chúng chỉ ~1 view — con số này đo lỗi phân phối, không đo nội
 dung. Nhưng tool đang đối xử với chúng như video bình thường, ở 2 chỗ:

1. **Số "mới nhất" đóng băng thành số hiện tại.** Bài đã xóa trên Facebook
   vẫn hiện "22 view" in đậm, chỉ có một icon cảnh báo nhỏ; "Tổng view"
   của video và xếp hạng theo view vẫn cộng số đó vào. Nhìn vào tưởng bài
   vẫn sống và page vẫn có từng đó view, trong khi thực tế là 0.
2. **Mốc 48h của bài đã xóa vẫn nuôi trung vị và KPI.** `analytics._marks`
   lấy mọi mốc 48h mà không lọc trạng thái bài đăng, nên 4 con số ~1 view
   kéo trung vị page xuống thấp, khiến video sau nhìn "gấp mấy lần trung
   vị" một cách giả tạo. KPI tuần này / tuần trước cũng tính chúng vào.

## Hành vi hiện tại (đã kiểm code ngày 06/11)

- `api/src/reels_api/metrics.py` — `measure()`: đọc `reel_insights` lỗi thì
  chỉ ghi `metrics_error`, giữ nguyên số cũ trong DB; `due_posts()` chỉ
  chọn bài `_is_published` (published, hoặc scheduled đã tới giờ). Mốc 48h
  viết một lần trong cửa sổ 48–72h sau khi đăng, không bao giờ viết lại.
- `api/src/reels_api/analytics.py` — `_marks()`: join `PostMetrics` với
  `window == "48h"`, **không lọc `Publication.status`**; `medians()` (60
  ngày, `MIN_SAMPLES = 5`) và `kpis()` (tuần này / tuần trước) đều tính từ
  marks đó.
- `web/src/components/PostMetrics.tsx` — `viewsOf()` trả
  `post.metrics.latest?.views ?? -1`; `posts/page.tsx` `totalViews()` cộng
  mọi bài có `viewsOf >= 0`. Bản compact hiện `latest.views` in đậm + icon
  cảnh báo, lỗi chỉ nằm trong tooltip. Nút "Cập nhật view" chỉ hiện khi
  bài còn public (`isPublic`).
- `api/src/reels_api/jobs.py` — `run_check_job`: `reel_status` trả None
  (Facebook không còn reel) thì `_close()` đặt status `"deleted"` (nếu
  bài đã từng live), `closed_by` None nên UI hiện "Xóa: Trên Facebook".
  Check tự động chỉ xếp hàng cho bài scheduled quá giờ; bài published
  phải bấm "Kiểm tra" tay mới đổi trạng thái.

## Yêu cầu

1. **Bài đã xóa / đã hủy không nuôi trung vị và KPI.** `_marks()` loại
   các `Publication` có status `"deleted"` hoặc `"cancelled"` — áp cho
   `medians()`, `kpis()` và `of_post()`/`times_median`. Không xóa dòng
   `PostMetrics` đã lưu trong DB.
2. **Số "mới nhất" của bài đã xóa không tính vào tổng.** `viewsOf()` trả
   `-1` với bài có status `"deleted"` hoặc `"cancelled"` (hoặc payload
   API trả `latest` null với các bài này) để "Tổng view" và sắp xếp theo
   view loại chúng ra. Dòng số liệu trong DB giữ nguyên làm lịch sử.
3. **Hiển thị rõ là số lịch sử.** Bài đã xóa hiện số cuối dạng "lúc xóa:
   22 view (đo lúc ...)" thay vì "22 view" in đậm như bài đang sống; lỗi
   "Facebook không còn reel này" hiện rõ bằng chữ, không chỉ icon/tooltip.
   Mốc 48h vẫn hiện trong lịch sử của chính bài đó.
4. **Không đổi:** quy tắc mốc 48h viết một lần, không viết lại; bài live /
   scheduled đo như cũ; tab "Đã hủy/xóa" giữ nguyên; "Cập nhật view" vẫn
   chỉ cho bài live.

## Test (TDD theo AGENTS.md: viết test lỗi trước rồi sửa)

- `api/tests/test_analytics.py`: bài deleted có mốc 48h không nằm trong
  median của page, không nằm trong KPI tuần.
- `api/tests/test_metrics.py`: đo bài đã xóa lỗi thì `metrics_error` được
  ghi, số cũ giữ nguyên (giữ hành vi này); `due_posts()` không chọn bài
  deleted.
- Web: `viewsOf` / `totalViews` loại bài deleted; `PostMetrics` hiển thị
  dạng "lúc xóa" với bài deleted.
- Chạy full suite api + web trước khi báo xong.

## Bàn giao

Branch riêng, PR với báo cáo 3 phần theo AGENTS.md (đổi gì, kết quả test
thật, cần người xem lại chỗ nào). Không tự merge. Không động production.
