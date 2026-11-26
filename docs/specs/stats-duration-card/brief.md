# Brief: Thẻ "Thời lượng nào hiệu quả nhất" — trang Thống kê

> Bản đã sửa sau review với code trên main (26/11): đo độ dài bằng `mp4_seconds`, 3 nhóm thay vì 5, loại bài đã gỡ, rõ biên nhóm.

Ngày: 26/11/2026. Người viết: Muse (phân tích).
User chốt: viết brief thẻ thời lượng trên trang Thống kê (26/11 10:17, bấm nút "Viết brief thẻ thời lượng"). Anh đọc brief này trước, rồi tự gửi coder.

## 0. Bối cảnh

- Trang Thống kê (`/stats`, PR #345, merge 25/11) so sánh các page với nhau: lượt xem, tiếp cận, tương tác, share/view, trung vị 48h, verdict 48h, thời gian xem, xem TB, khung giờ hiệu quả nhất. Chưa có phân tích nào theo độ dài video.
- Phác họa `phac-hoa-trang-thong-ke` v11 đã liệt kê cột "Thời lượng hiệu quả nhất" trong bảng so sánh 17 cột, nhưng PR #345 KHÔNG làm cột này.
- Câu hỏi cần trả lời: nhóm thời lượng nào (ngắn 45–60s hay dài hơn) có median views_48h cao nhất — để quyết giữ format ngắn hay quay lại dài. Số 48h lô ngày 12 (test format ngắn) đủ dần trong ngày 26/11 (12:00/18:00/21:00); thẻ này dùng chính số đó khi đủ mẫu.
- Tín hiệu sớm (chưa phải kết luận): Tiệm 45–60s trung bình 665 view/7 ngày, >60s chỉ 168 (ảnh chụp của user, 23/11). Thẻ phải tính bằng median, không phải trung bình.

## 0.1. Lưu ý về xác minh — đọc trước khi code

- GitHub API trả 404 cho repo `tuananh219ln/Reels-Studio` từ 20/11 — Muse KHÔNG đọc lại được code qua GitHub. Brief này viết từ code trên main đọc qua bản clone VM (`~/workspace/reels-studio/repo-src`, fetch 26/11 10:10, HEAD `bd94b12` = PR #360).
- Những gì ghi **ĐÃ XÁC MINH (main)** là đọc từ file trên main. Những gì ghi **CẦN KIỂM CHỨNG** là việc coder/T3 phải xác nhận trên repo local trước khi code — không tự suy diễn thêm.
- Base branch: main hiện tại. PR này chỉ thêm thẻ thời lượng, không sửa hành vi hiện có của `/api/stats` hay trang Thống kê.

## 1. Hiện trạng (ĐÃ XÁC MINH trên main)

- `GET /api/stats` (`api/src/reels_api/routes_stats.py:17`): một hàng cho mỗi page; tham số `days` ∈ {7, 28, 90}, `platform` ∈ {facebook, instagram}, `page_ids` tối đa 30. Hàng Facebook dựng từ các hàm của dashboard từng page (`page_stats.py`), không lưu số mới (quyết định `docs/decisions/2026-11-25-stats-page.md`: chỉ so sánh, không cộng tổng; số thiếu hiện `None`, không hiện 0).
- `page_dashboard.content(db, page, days)` (`page_dashboard.py:262`): trả từng bài đã đăng trong kỳ, mỗi bài có `views_48h` (lấy từ mốc 48h của `PostMetrics`, `page_dashboard.py:229`) và `video` (qua `_video()`). `page_stats.py:55` đã dùng `post["views_48h"]` để lập danh sách "Đang đo" (bài chưa đủ 48h).
- Độ dài video: `Video.mp4_seconds` (`models.py:352`), độ dài file MP4 do render đo (`jobs.py:962`); `post_links.py:327` đã dùng nó.
- Ngưỡng mẫu: `analytics.MIN_SAMPLES = 5` (`analytics.py:29`): dưới 5 bài đã đo thì trung vị của page "means little" — không so sánh bài nào với nó. Median 48h của page tính bằng `analytics.medians()` (`analytics.py:71`).
- Trang web (`web/src/app/(app)/stats/page.tsx`): bảng so sánh dùng Ant Design `Table` + `ColumnPicker` (nhớ cột đã chọn), kỳ 7/28/90, tab Facebook/Instagram/TikTok; các cột định nghĩa trong `FACEBOOK_CELLS` (mỗi cột có `group`, `tip`, `value` cho CSV, `render`). Chưa có cột hay thẻ nào về thời lượng.

## 2. Mục tiêu

Thêm thẻ "Thời lượng nào hiệu quả nhất" trên trang Thống kê, trả lời cho từng page: nhóm thời lượng nào có median views_48h cao nhất — kèm bằng chứng (median + số mẫu từng nhóm), để user quyết format.

## 3. Spec

### 3.1. Backend — thêm trường vào hàng Facebook của `GET /api/stats`

- Thêm `duration_buckets` vào dict hàng Facebook trong `page_stats.py::_facebook_row` (KHÔNG sửa các trường hiện có).
- Mỗi phần tử: `{"bucket": "<45s" | "45–60s" | ">60s", "videos": n, "median_views_48h": int | null, "best": bool}`. Ba nhóm (không phải năm): kỳ 7 ngày chỉ có vài ngày bài đủ 48h, chia nhỏ hơn thì gần như nhóm nào cũng thiếu mẫu.
- Biên nửa mở: 45 ≤ x < 60 thuộc "45–60s"; đúng 45,0s vào "45–60s", đúng 60,0s vào ">60s".
- Nguồn số (ĐÃ XÁC MINH): `page_dashboard.content(db, page, days)["posts"]` — cùng kỳ ngày, cùng tập bài như các số khác của hàng.
- Độ dài video = `Video.mp4_seconds` (`models.py:352`, độ dài file MP4 do render đo bằng ffprobe, `jobs.py:962`). Một truy vấn `Video.id, mp4_seconds` cho các video của page. Video chưa có `mp4_seconds` thì bỏ khỏi mẫu.
  - KHÔNG cộng `fitted_seconds` các cảnh: phải tải từng cảnh và tính lại giọng đọc cho mọi bài, và sửa chữ sau khi đăng làm `voice_seconds` thành None nên số lệch.
  - KHÔNG dùng `Publication.duration_sec` (`models.py:1121`): chỉ có cho bài ngoài app.
- Chỉ tính bài `status == "published"` có `views_48h`. Bài `deleted` (vẫn nằm trong `content()` kèm `views_48h`) KHÔNG tính, giống `analytics.py`; bài chưa đủ 48h cũng không tính.
- Nhóm có < `analytics.MIN_SAMPLES` (5) bài → `median_views_48h = null` (hiện "Chưa đủ mẫu").
- Median: `statistics.median` trên `views_48h` của nhóm, trong kỳ đã chọn (7/28/90). Không có hàm dùng chung: `analytics.medians()` tính trên 60 ngày cho cả page.
- `best = true` cho nhóm có median cao nhất, chỉ khi ≥ 2 nhóm có median; đồng hạng thì đánh dấu tất cả.
- Tính riêng từng page, không cộng gộp (đúng quyết định 25/11).
- Chỉ Facebook ở v1. Instagram không có `views_48h` (`instagram_content` không trả) nên hàng IG không có `duration_buckets`.

### 3.2. Frontend — thẻ mới trên trang Thống kê

- Thêm `Card` mới đặt dưới bảng so sánh (trong `ComparisonTable`, sau `Card` của bảng; thêm kiểu vào `StatsFacebookRow`, `web/src/lib/api.ts`), tiêu đề "Thời lượng nào hiệu quả nhất".
- Mỗi page một hàng: tên page + 3 ô nhóm. Mỗi ô hiện median views_48h (dạng số gọn, dùng `formatNumber` đã có) + số mẫu `n` bên dưới; nhóm `best` tô đậm/đánh dấu (Tag "Tốt nhất" hoặc viền đậm — theo ngôn ngữ Ant Design đã dùng trong trang); nhóm chưa đủ mẫu hiện "Chưa đủ mẫu (n)".
- Thẻ nhắc rõ trung vị tính theo kỳ đang chọn, khác "Trung vị 48h" (60 ngày) của bảng.
- Chỉ hiện trên tab Facebook. Tab Instagram/TikTok không hiện thẻ này.
- Kỳ ngày 7/28/90 áp dụng như các số khác (thẻ đọc cùng response `GET /api/stats`, không gọi thêm request).
- Không thêm cột mới vào bảng so sánh, không đụng CSV export của bảng (thẻ không phải cột; CSV đợt này không xuất thẻ).

### 3.3. Vì sao là thẻ, không phải cột

- Phác họa v11 liệt kê cột "Thời lượng hiệu quả nhất" — một ô chỉ chứa được đáp án ("45–60s"), không chứa được bằng chứng (median + số mẫu từng nhóm). Thẻ hiện đủ 3 nhóm nên user thấy được nhóm nào thắng và thắng bao nhiêu. Đáp án "nhóm tốt nhất" của thẻ chính là giá trị cột đó.

## 4. Tests + docs (chuẩn repo)

- "Done" = lint + typecheck pass, tests có + pass, docs cập nhật cùng PR (theo `AGENTS.md` của repo).
- Test (`api/tests/test_page_stats.py`): đủ/thiếu mẫu, biên 45/60, đồng median, chỉ 1 nhóm, loại bài đã gỡ và video chưa có độ dài, IG không có trường, các trường cũ không đổi.
- Docs: `docs/architecture.md` (đoạn `GET /api/stats`) và `docs/project.md` (dòng Thống kê).
- Viết decision doc `docs/decisions/2026-11-26-stats-duration-card.md` cùng PR (ngắn: thẻ so sánh từng page, median 48h, ngưỡng 5 mẫu, chỉ Facebook v1).

## 5. Kiểm chứng khi xong (acceptance)

- Đối chiếu tay trên 2 page: tính median views_48h từng nhóm từ `list_post_stats` (hoặc tab Nội dung từng page) và so với số thẻ hiện — phải khớp.
- Kiểm nhóm của video đã biết: video Ăn Lành ~37s vào nhóm <45s; video Threads ~75s vào nhóm >60s; video FoodDose ~25s vào nhóm <45s.
- Kiểm trạng thái "Chưa đủ mẫu" xuất hiện đúng nhóm < 5 bài; kiểm `best` chỉ xuất hiện khi ≥ 2 nhóm có median. Kỳ 7 ngày có thể phần lớn là "Chưa đủ mẫu": xem kỳ 28 ngày.
- Kiểm không đổi: các trường cũ của `GET /api/stats` và bảng so sánh hiện như trước (so sánh response trước/sau).

## 6. Ngoài phạm vi

- Trending topics/chủ đề hot (không có API chính thức — user chốt 26/11: giữ thủ công, không làm trong PR này).
- Dashboard từng page và báo cáo 48h: không đưa thẻ vào đó đợt này.
- Gợi ý tự động đổi format video: thẻ chỉ hiện số liệu, quyết định là của user.
- Instagram: không làm ở v1 (xem 3.1).
