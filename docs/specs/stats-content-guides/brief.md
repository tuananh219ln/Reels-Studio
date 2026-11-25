# Brief: 1 PR gộp 3 món — trang Thống kê + cải tiến Nội dung/Tổng quan theo Meta + mục "Tất cả hướng dẫn"

Ngày: 25/11/2026. Người viết: Muse (phân tích). Review: T3 (Mac) — đối chiếu code local trước khi code.
User chốt: làm cả 3 trong 1 PR (không tách 3 PR).

## 0. Bối cảnh

- **Trang Thống kê:** phác họa `phac-hoa-trang-thong-ke` v11 (artifact trong chat Phân tích Reels Studio) — so sánh xuyên page, không cộng tổng. Đã chốt hướng lần 3 (chỉ so sánh) và 15 món bổ sung.
- **Cải tiến Nội dung/Tổng quan:** đối chiếu 4 màn Meta Business Suite (ảnh 24–25/11) với tool live, kiểm tra 25/11 01:48 (FoodDose `/fanpages/12` + Già `/fanpages/7`).
- **Mục "Tất cả hướng dẫn":** phân tích 25/11 ~02:00 — tính năng Hướng dẫn đã có dạng nút từng màn, chưa có mục sidebar.

## 0.1. Lưu ý về xác minh — đọc trước khi code

- GitHub API trả 404 cho repo `tuananh219ln/Reels-Studio` từ 20/11 (cả public API lẫn GitHub App) — Muse KHÔNG đọc lại được code qua GitHub. Brief này viết từ: (1) kiểm tra live tool 25/11 01:48, (2) đọc code TRỰC TIẾP trên repo local của Mac ngày 25/11 (`ContentLibrary.tsx`, `AppShell.tsx`, `GuideButton.tsx`, `page_dashboard.py`), (3) phác họa v11, (4) phân tích guides ngày 24/11.
- Những gì ghi **ĐÃ XÁC MINH (local)** là đọc từ file trên Mac. Những gì ghi **CẦN KIỂM CHỨNG** là việc T3 phải xác nhận trên repo local trước khi code — không tự suy diễn thêm.
- Base branch: code trên Mac hiện đã có `web/src/components/GuideButton.tsx` + `page_dashboard.py` có `gate()` — PR này base trên nhánh local hiện tại (code mới nhất trên Mac). T3 xác nhận tên nhánh + tình trạng merge của `feature/custom-link-excel` khi review.

## 1. Phần A — Trang Thống kê mới (route đề xuất `/stats`)

### Hiện trạng

Chưa có trang này. Dashboard `/fanpages/[id]` chỉ xem từng page; PageCompare (`compare()` trong `page_dashboard.py`) chỉ so cùng video FB vs IG; `/fanpages` không có hàng tổng. (ĐÃ XÁC MINH: audit 24/11 + đọc `page_dashboard.py`.)

### Sidebar

Thêm vào `NAV` trong `web/src/components/AppShell.tsx`, nhóm **"Đăng và kiếm tiền"** (`group:post`), sau `/posts` (Bài đăng), trước `/fanpages` — label **"Thống kê"**, kèm badge **"Mới"** (theo mẫu badge số bài lỗi trên `/articles` trong cùng file). Phương án để nhóm TỔNG QUAN đã được nêu nhưng user chưa chọn — giữ ĐĂNG VÀ KIẾM TIỀN theo phác họa.

### Dữ liệu — chỉ dùng endpoint đã có, gom ở client

Không thêm endpoint tổng hợp trừ khi T3 thấy gọi N+1 quá nặng. Nguồn cho mỗi page (ĐÃ XÁC MINH trong `page_dashboard.py`):

- `dashboard()` — totals views/reach/engagements + series lượt xem theo ngày, có kỳ trước để tính So kỳ trước.
- `gate()` — trung vị view 48h, verdict, danh sách winners (GATE_FIRST=14, GATE_LAST=30, GATE_MEDIAN=1000, GATE_TOP=10000, GATE_CHANGE_MEDIAN=500, GATE_CHANGE_SHARE=0.001).
- `content()` — view 48h + `times_median` + `is_winner` từng bài.
- `best_times()` — khung giờ hiệu quả nhất, ĐÃ CÓ SẴN (BEST_MIN_POSTS=6, BEST_MIN_PER_HOUR=2, BEST_SHOWN=3), chỉ cần hiện lên.
- `instagram_dashboard()` + `instagram_content()` cho tab IG.

Khoảng ngày 7/14/28 (như phác họa; `PERIODS = (7, 28, 90)` của `page_dashboard.py` vẫn giữ cho dashboard từng page). Mặc định chọn 6 page "Của tôi" (tool fanpage_id 6, 7, 8, 9, 10, 12); 2 page Looper (5, 11) không chọn mặc định. Dropdown chọn page chia 2 nhóm như phác họa.

### Bảng so sánh (17 cột)

Tên page | Lượt xem | View 48h | Chia sẻ | Share/view | Trung vị 48h | Verdict 48h | Bình luận | Người xem | Hiển thị | So kỳ trước | Khán giả chính | Xem ≥1 phút | Thời gian xem | Chưa theo dõi % | Thời lượng hiệu quả nhất | Dashboard (link `/fanpages/[id]`).

### Kết quả kiểm tra nguồn số (ĐÃ XÁC MINH trên `page_dashboard.py`)

Docstring đầu file: *"Numbers Facebook does not give (followers against non-followers, traffic sources, unfollows, 3-second views) are left out rather than guessed."*

| Cột | Kết luận |
|---|---|
| Verdict 48h, Trung vị 48h, Video thắng | `gate()` — CÓ |
| Bình luận, Chia sẻ, Share/view | `post_numbers` + `gate()` — CÓ |
| So kỳ trước (số tuyệt đối) | `dashboard()` totals có kỳ trước — CÓ (chỉ hiện số tuyệt đối, không %) |
| Thời gian xem (tổng) | Suy ra được từ `avg_watch_seconds × views` từng bài (công thức như `_post_sums`) — CÓ |
| Khung giờ hiệu quả nhất | `best_times()` — CÓ SẴN |
| Người xem (unique viewers) | `PostMetrics` không có trường này; gần nhất là reach ("Số người đã thấy reel"). CẦN KIỂM CHỨNG: FB post insights có trả viewers riêng không; nếu không thì dùng reach và ghi chú rõ, hoặc bỏ cột |
| Hiển thị (impressions) | Không lưu. CẦN KIỂM CHỨNG: FB post insights có trả impressions không; nếu không thì bỏ cột |
| Xem ≥1 phút | Docstring nói 3-second views không có → gần như chắc chắn KHÔNG CÓ. CẦN KIỂM CHỨNG rồi bỏ cột nếu không có — không bịa số |
| Chưa theo dõi % | Docstring nói followers-against-non-followers không có → KHÔNG CÓ. Bỏ cột (phác họa có ghi chú "cần kiểm tra nguồn số" — đây là kết quả kiểm tra) |
| Khán giả chính | FB không có trong `dashboard()`; IG có `audience` (`instagram_dashboard`). CẦN KIỂM CHỨNG: chỉ hiện cho IG, FB hiện "—", hoặc bỏ cột |

### Biểu đồ + dải (theo phác họa v11)

- Biểu đồ lượt xem theo ngày (mỗi page 1 đường, từ `dashboard()` series) + biểu đồ tương tác theo ngày (từ engagements series), đồng bộ dropdown + khoảng ngày. Chỉ số tuyệt đối, không % tăng.
- Dải Mới đăng đang đo 48h (`content()` bài có `views_48h` null), dải Video thắng ≥10× (`gate().winners`), dải Chia sẻ nhiều nhất (share/view), dải Tương tác nhiều nhất, thẻ Khung giờ hiệu quả nhất (`best_times()`).
- Mỗi dòng bảng link xuống dashboard của page đó (`/fanpages/[id]`).

### Chọn cột + Xuất CSV + tab nền tảng

- Dùng chung component chọn cột đã nâng cấp ở mục 2.3 (tìm kiếm + nhóm + kéo-thả + Hủy/Áp dụng); CSV xuất đúng cột đang hiện (mẫu `downloadCsv` trong `ContentLibrary.tsx`).
- Tab nền tảng FB/IG đổi toàn bộ số liệu theo nền tảng (IG dùng `instagram_dashboard`/`instagram_content`); TikTok hiện trạng thái trống (chưa có nguồn số). Segmented gọn như phác họa v11.

### Không làm ở trang này

Dải tổng gộp (đã bỏ ở v6), % tăng trưởng, thẻ KPI từng page, bảng bài đăng từng page, thu nhập, lượt theo dõi mới theo video.

### Số thật để kiểm chứng

Già: trung vị 48h 166, verdict "Đổi hook và trụ nội dung (không đổi tên Page)", view 48h cao nhất 670, đã đo 37/14/30, chưa có winner. Threads: 11.231 view/28 ngày, 536 tương tác, video "Sếp hứa 18 triệu" +17,8× trung vị, khung giờ 21:00 và 12:00 mạnh nhất, thời lượng 45–60 giây +581%.

## 2. Phần B — Tab Nội dung + Tổng quan (dashboard `/fanpages/[id]`)

### 2.1. Thêm cột vào `ContentLibrary.tsx`

**Hiện trạng — ĐÃ XÁC MINH (code + live 25/11 01:48):** 11 cột trong `COLUMNS` (Lên lúc, Trạng thái, Lượt xem, Tiếp cận, Cảm xúc, Bình luận, Chia sẻ, Theo dõi, Xem TB, View 48 giờ, So với trung vị) + cột Bài đăng cố định + cột thao tác cuối. Dữ liệu từ `GET /fanpages/{id}/content?days=`, mỗi bài có `numbers` {views, reach, reactions, comments, shares, avg_watch_seconds, followers, measured_at} (xem `_content_row` trong `page_dashboard.py`) + `views_48h`, `times_median`, `is_winner` (cờ Winner đã có trong code — `data-testid="winner-flag"` — chỉ hiện khi `is_winner` đúng; Già chưa có winner nên live không thấy).

**Thêm:** Lượt lưu, Lượt click vào liên kết, Người xem, Lượt hiển thị, và tổng Thời gian xem (bên cạnh Xem TB).

- Đây KHÔNG phải chỉ thêm cột hiển thị: 4 trường mới chưa có trong `numbers` → phải mở rộng pipeline đo chỉ số FB (`PostMetrics` + chỗ kéo post insights) rồi mới thêm vào `_content_row` + `COLUMNS`. **CẦN KIỂM CHỨNG:** FB post insights trả những trường nào trong 4 trường trên (lưu ý: IG đã có `saves` trong `_instagram_numbers` — FB thì chưa).
- Tổng Thời gian xem: tính được từ dữ liệu đã có (`avg_watch_ms × views` từng bài, công thức như `_post_sums`) — không cần kéo thêm.
- Quy tắc: trường nào FB không trả thì cột hiện "—" (mẫu `latest()` trả null → "—"), không bịa số, không đoán. Theo đúng docstring `page_dashboard.py`.

### 2.2. Bộ lọc loại nội dung trên tab Nội dung

**Hiện trạng:** tab chỉ liệt kê reel (`content()` lọc `Publication.video_id IS NOT NULL`, docstring: *"Reels only: an article has no video to show and no views"*). Không có bộ lọc nào.

**Yêu cầu:** thêm lọc Tất cả / Reels / Ảnh / Bài viết. **CẦN QUYẾT ĐỊNH KHI REVIEW (T3):** bài viết (article) không có trong endpoint này — hoặc mở rộng `content()` để gồm cả article (số view hiện "—", đối chiếu cách `/articles` đo "Số 48h"), hoặc bỏ lọc ở tab này và để việc so sánh định dạng cho mục 2.5 + trang Thống kê. Không tự ý chọn — ghi quyết định vào PR.

### 2.3. Nâng cấp hộp chọn cột (dùng chung cho tab Nội dung và bảng Thống kê)

**Hiện trạng — ĐÃ XÁC MINH:** Popover "Cột hiện trong bảng", `Checkbox.Group` phẳng 11 ô, tick là áp dụng ngay, lưu localStorage key `"page-content-columns"` (`useRememberedColumns`). Không tìm kiếm/nhóm/kéo-thả/Hủy-Áp dụng.

**Yêu cầu:** hộp chọn kiểu Meta (ảnh 25/11 01:45): ô tìm kiếm, nhóm cột (Chi tiết về nội dung / Hiệu quả / Lượt tương tác), kéo-thả sắp xếp lại cột, nút Hủy / Áp dụng (chỉ áp dụng khi bấm Áp dụng, Hủy thì bỏ thay đổi). Giữ nguyên lưu localStorage + key cũ để không mất lựa chọn đã lưu của user. Dùng chung 1 component cho cả 2 bảng.

### 2.4. Gộp cụm thao tác mỗi dòng thành 1 nút

**Hiện trạng — ĐÃ XÁC MINH (code + live):** cột cuối rộng 170px, `Flex gap={4}` gồm 3 nút: `VideoActions` (icon ⋮ dọc — menu 9 mục: Mở video, Đăng bài/hàng chờ/job…, Tải MP4, Nhân bản, Nhân bản y hệt, Nhân bản xáo cảnh, Tạo bản TikTok, Chuyển sang nhóm khác, Xóa video), `ManagedPostActions` (pill "Thao tác bài đăng" ~125px — mở drawer: Phân tích bài đăng, Cập nhật view, Đã bình luận/Cập nhật bình luận, Xem Reel, Thử lại, Kiểm tra, Sửa link reel, Xóa), `RowMenu` (icon ••• ngang — menu 3 mục: Mở video, Mở reel trên Facebook, Cập nhật view).

**Yêu cầu:** chỉ còn 1 nút icon ••• mỗi dòng, mở 1 menu/ngăn duy nhất chứa hợp nhất các mục trên (bỏ trùng lặp: "Mở video" xuất hiện 2 lần, "Cập nhật view" 2 lần, "Xóa" 2 lần). Giữ lại các mục riêng của drawer (Phân tích bài đăng, Cập nhật bình luận, Sửa link reel). Không thêm mục "Chỉnh sửa" — tool không sửa được video trên Facebook. Cột thao tác thu hẹp tương ứng (không giữ width 170).

### 2.5. Mục "Định dạng nội dung hàng đầu" trên tab Tổng quan

**Hiện trạng:** `dashboard()` không có breakdown theo định dạng. **Yêu cầu:** thêm 1 mục trên tab Tổng quan so sánh hiệu quả Reels vs Ảnh (theo view 48h/trung vị hoặc lượt xem). **CẦN KIỂM CHỨNG:** nguồn số cho ảnh lấy từ đâu (articles + "Số 48h" của `/articles`) — T3 xác nhận khi review; nếu nguồn số chưa đủ thì mục này làm sau, không chặn PR.

## 3. Phần C — Sidebar "Tất cả hướng dẫn" (route `/guides`)

### Hiện trạng — ĐÃ XÁC MINH (local)

`web/src/components/GuideButton.tsx` — nút "Hướng dẫn" ở đầu từng màn, gọi `api('/guides?screen=${screen}')`, mở Drawer 860px, nhiều guide thì Segmented chuyển, đọc bằng `MarkdownReader`. 5 guide Markdown trong `api/src/reels_api/guides/` (affiliate.md, custom-link.md, knowledge.md, videos.md, videos-editor.md). Quyết định: `docs/decisions/2026-11-25-in-app-guides.md` (guide là của app, trong code, đổi cùng PR với tính năng — KHÔNG phải tài liệu nhóm trong DB).

### Yêu cầu

- 1 route mới `/guides` + 1 dòng trong `NAV` ở `AppShell.tsx` (nhóm **"Tài nguyên"** `group:library`, sau `/knowledge` Kho kiến thức) — label **"Tất cả hướng dẫn"**, icon `QuestionCircleOutlined` (cùng icon với GuideButton).
- Trang `/guides` liệt kê tất cả guide gom theo màn (Affiliate, Video, Kho kiến thức...), bấm vào đọc bằng `MarkdownReader` có sẵn (cùng bộ đọc với GuideButton + `TopicDocs.tsx`).
- Dữ liệu: `GET /api/guides` không lọc screen — **CẦN KIỂM CHỨNG** trong `routes_guides.py` rằng không truyền screen thì trả tất cả guide.
- Không thay đổi: nút GuideButton từng màn giữ nguyên; không đưa guide vào tab Tài liệu của nhóm; không cho MCP đọc guide.
- Phạm vi mỏng: mới 5 guide / 3 màn — trang gom theo màn, viết thêm guide dần theo luật "màn nào đổi thì viết guide màn đó" (không thuộc PR này).

## 4. Không làm (cả 3 phần)

- % tăng trưởng (FB hiện +100% giả — chỉ hiện số tuyệt đối và So kỳ trước dạng số tuyệt đối).
- Lượt theo dõi mới theo video (Facebook không trả qua API — dashboard đã hiện "—").
- Thu nhập (chưa có dữ liệu).
- "Kế hoạch hàng tuần" kiểu Meta (nhiệm vụ onboarding "Đăng một quảng cáo" — không bê nguyên).
- Tab Tin / story (tool không quản lý story).
- Chia tự nhiên/quảng cáo (tool không chạy ads).
- "Chỉnh sửa/Xóa thước phim", "Bật remix" của Meta (tool không sửa/xóa được video trên Facebook).
- Nút "Tạo 3 biến thể" — không thuộc PR này (đã có trong PR #343, chỉ hiện với video winner; Già chưa có winner nên chưa kiểm chứng được vị trí).

## 5. Kiểm chứng (acceptance)

- `/stats`: mở được từ sidebar sau Bài đăng; mặc định so sánh 6 page của user; không còn con số tổng cộng dồn nào; 17 cột đúng định nghĩa; Verdict 48h của Già = "Đổi hook và trụ nội dung", trung vị 166; video "Sếp hứa 18 triệu" hiện +17,8× ở dải thắng; cột không có nguồn số hiện "—" kèm ghi chú, không hiện số bịa.
- Tab Nội dung: cột mới chỉ hiện khi FB trả số, còn lại "—"; lọc loại nội dung (nếu làm theo hướng mở rộng `content()`) hoạt động; hộp chọn cột có tìm kiếm/nhóm/kéo-thả/Hủy-Áp dụng và giữ lựa chọn đã lưu; mỗi dòng chỉ còn 1 nút ••• với đủ mục (không mất Phân tích/Cập nhật bình luận/Sửa link reel).
- Tổng quan: mục Định dạng nội dung hàng đầu hiện Reels vs Ảnh (hoặc ghi rõ làm sau nếu nguồn số chưa đủ).
- `/guides`: mở từ sidebar sau Kho kiến thức; liệt kê đủ 5 guide gom theo màn; đọc được nội dung; nút từng màn không đổi.
- Không regression: dashboard từng page, cửa đo 48h, tab Tài liệu, Xuất CSV vẫn chạy. Chạy `ruff check` + `ruff format --check` với đúng `ruff.toml` của repo trước khi báo xong.
