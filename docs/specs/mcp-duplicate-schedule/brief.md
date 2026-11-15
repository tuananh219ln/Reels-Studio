# Brief Reels Studio — Thêm 2 tool MCP: nhân bản y hệt + hẹn giờ qua hàng chờ

> Soạn 15/11/2026 theo quyết định của user (chủ sản phẩm).
> Cách làm theo lệ của team: đọc AGENTS.md + docs/decisions.md trước;
> nhánh riêng; TDD (viết test trước); chạy đủ test api + web; báo cáo
> 3 phần theo AGENTS.md; không tự merge; chạy inline, không dùng
> subagent.

## Bối cảnh (đã kiểm chứng 15/11 trên main)

User muốn nhân bản 10 video nhiều view nhất của page Ăn Ngon Sống
Khỏe (trong tool: 90, 167, 68, 45, 85, 82, 72, 83, 63, 166) sang
nhóm test (knowledge_topic_id 10, "Nhóm test") để đăng trên page mới
Ăn Ngon Mỗi Ngày (fanpage id 10), mỗi ngày 4 video vào 08:30 /
11:30 / 15:30 / 18:00, bắt đầu 16/11.

Nút "Nhân bản y hệt" đã có trên web (`POST /videos/{id}/duplicate`,
`api/src/reels_api/duplicate.py`, quyết định
`docs/decisions/2026-11-14-duplicate-video.md`), nhưng **MCP không có
tool nào cho việc này**: rà hết `api/src/reels_api/mcp_server.py`
trên main không có chữ `duplicate` nào, và gọi thẳng REST API bằng
token MCP bị chặn 403 (`origin_not_allowed`). Hẹn giờ đăng cũng vậy:
MCP không có tool hẹn giờ/đăng bài (giới hạn cố tình từ đầu). Muốn
làm 10 video này hiện chỉ có cách mở trình duyệt bấm tay từng cái —
chậm và dễ sót.

Brief này thêm đúng 2 tool MCP, dùng lại logic server đã có, không
viết lại luật kiểm tra riêng.

## Yêu cầu 1 — tool MCP `duplicate_video`

- Tên `duplicate_video`, theo phong cách đặt tên hiện có
  (`render_video`, `update_video`, `set_audio`). Scope yêu cầu:
  `reels:write`, giống các tool ghi khác.
- Đăng ký trong `api/src/reels_api/mcp_server.py`, theo mẫu các
  tool ghi có sẵn: decorator `@tool("Nhân bản y hệt", read=False)`
  + chạy qua `run_in_threadpool(invoke, ..., write=True)`.
  `external` chỉ đặt `openWorldHint` (tool có chạm dịch vụ bên ngoài
  không), không liên quan endpoint: nhân bản không gọi AI hay
  Facebook nên để mặc định `False`.
- Hành vi = **y hệt route web `POST /videos/{video_id}/duplicate`**
  (`api/src/reels_api/routes_videos.py:1059`): load video gốc theo
  id (không có → 404 `video_not_found`); gốc chưa có kịch bản →
  409 `no_script` ("Video gốc chưa có kịch bản để nhân bản"); gọi
  `duplicate.duplicate_video(db, get_storage(), source, me.user_id)`
  trong `api/src/reels_api/duplicate.py` (import thêm module
  `duplicate` trong `mcp_server.py` — hiện chưa import).
- **Không kiểm tra quyền sở hữu video gốc**: route web cũng không
  kiểm tra (docstring: "The source is only read, never locked: a
  teammate may keep working on it"). Bản copy mang
  `created_by_id` = người gọi. Đây là hành vi đã chốt, giữ nguyên.
- Không gọi AI. Không copy MP4 (`mp4_key`, `mp4_seconds`, `qc`,
  `rendered_signature`, `rendered_at` nằm trong `_VIDEO_SKIP` của
  `duplicate.py`): bản copy phải render lại rồi mới đăng được.
- Tham số thêm so với route web: `knowledge_topic_id` (tùy chọn,
  int). Nếu truyền vào thì sau khi copy xong, đặt nhóm của bản copy
  thành nhóm đó rồi mới commit. Nhóm không tồn tại → 404. Không yêu
  cầu nhóm có `can_create` (bản copy đã có sẵn kịch bản, không viết
  kịch bản mới). Không truyền thì bản copy ở lại nhóm của video gốc
  (hành vi mặc định của route web). Đặt nhóm theo đúng việc route
  "Chuyển sang nhóm khác" (`move_video`) làm, không viết luật riêng.
- Tham số thêm `fanpage_id` (tùy chọn, int): **đè logo bằng logo
  của Page đích**. Lý do: chuyển nhóm không đổi kênh/logo (kênh nằm
  ở `options.brand_id`, bản copy giữ nguyên của video gốc), nên bản
  copy của video bật "Gắn logo" Ăn Ngon Sống Khỏe sẽ bị Page 10 từ
  chối ở bước hẹn giờ ("Video mang logo … chỉ đăng được lên Page của
  kênh đó"). Khi truyền `fanpage_id`:
  - Tìm kênh gắn với Page đó (`Brand.fanpage_id`, mỗi Page tối đa
    một kênh). Page không tồn tại → 404; Page chưa gắn kênh → 409
    kèm lời nhắc gắn kênh ở Quản lý kênh.
  - Gọi `brands.apply_video_options(db, copy, me.user_id,
    {"brand_id": brand.id, "logo_enabled": True})`: dùng lại đúng
    kiểm tra của ô "Kênh"/"Gắn logo" trên web (không phải chủ kênh →
    403, kênh chưa có logo → 400 `brand_has_no_logo`). Không viết
    luật riêng.
  - Lỗi nào ở bước này thì rollback cả bản copy (không để lại bản
    copy dở dang).
- Trả về: id + link của video mới, cùng dạng với các tool tạo video
  (`video_link`), kèm kênh/logo đang gắn (`brands.payload_of`) và
  `commission_warnings` như tool gắn sản phẩm (bản copy mang theo
  sản phẩm affiliate của video gốc, có thể là sản phẩm của đồng đội).
- Không đổi logic trong `duplicate.py` (danh sách `_VIDEO_SKIP`,
  cách copy file, layer, sound, sản phẩm affiliate giữ nguyên).
  Nhóm và kênh được đổi sau khi copy, trong tool.

## Yêu cầu 2 — tool MCP `schedule_video`

- **Nới một quyết định đã ghi, chủ sản phẩm đã chốt 15/11:**
  `docs/decisions/2026-11-09-page-owner-posts.md` ghi "MCP has no
  posting tool"; tool này là tool MCP đầu tiên dẫn tới một bài đăng
  Facebook. PR thêm `docs/decisions/2026-11-15-mcp-duplicate-schedule.md`
  ghi rõ việc nới này. Câu "Không tự render hay đăng" trong lời dặn
  chung của MCP (`instructions` trong `mcp_server.py`) sửa lại: chỉ
  gọi `schedule_video` khi thành viên yêu cầu rõ, và sau khi đã xem
  bản render bằng "Xem khung hình bản render" (`view_render_frames`),
  vì nút web "Thêm vào hàng chờ" vốn là bấm sau khi xem MP4.
- Tên `schedule_video`, cùng mẫu decorator
  (`read=False, external=True`: dẫn tới Facebook).
- Hành vi = **y hệt route web `POST /api/queue`**
  (`api/src/reels_api/routes_queue.py:139`, hàm `add`): lock video,
  chạy `page_queue.problem(db, video)` (video chưa render xong hoặc
  MP4 lỗi thời → 409 `not_queueable` kèm đúng lý do đó, không tự
  render hộ); xác định Page theo `_page_for` — `fanpage_id` truyền
  vào phải là Page của chính người gọi (`ensure_page_owner`, sai →
  403), bỏ trống thì lấy Page của người gọi thuộc nhóm của video;
  chạy `page_queue.problem(db, video, page)` (lệch brand, MP4 đã có
  trên Page đó); video đã trong hàng chờ → 409 `already_queued`;
  hàng chờ đủ 100 → 409 `queue_full`. Tạo `PageQueueItem` với
  `position = page_queue.next_position`, `auto_comment=True`.
  Import thêm `routes_queue` / `page_queue` trong `mcp_server.py`
  (hiện chưa import). Dùng chung logic với route, không viết lại
  luật kiểm tra riêng.
- Trả về: queue item vừa tạo, cùng dạng `_item_payload` của route
  (id, fanpage_id, fanpage, video{id, title, thumbnail_url},
  auto_comment, added_by, added_at).
- **Tool này không chọn giờ và không gọi Facebook.** Việc hẹn giờ
  là của worker fill có sẵn (`page_queue.fill`, chạy giữa các job):
  mỗi lượt worker lấy tối đa 1 video/Page, xếp vào khung giờ trống
  tiếp theo của Page trong 48h tới (khung cách giờ hiện tại ít nhất
  30 phút, các bài cách nhau ít nhất 30 phút). Giờ đăng lấy từ
  `post_times` của Page (riêng Page, không có thì lấy
  `plan_post_times` của nhóm). Không thêm tham số giờ cụ thể.
- Điều kiện tiên quyết (chủ sản phẩm tự làm 1 lần trên web, không
  phải việc của agent, không nằm trong tool): đặt `post_times` của
  fanpage 10 (Ăn Ngon Mỗi Ngày) thành
  `["08:30", "11:30", "15:30", "18:00"]` ở mục cài đặt trang "Hàng
  chờ"; xem giá trị hiện tại trước khi đặt. Page 10 phải gắn một
  kênh có logo ở Quản lý kênh (cho `duplicate_video(fanpage_id=10)`).

## Luồng dùng sau khi xong (đợt 10 video này)

1. `duplicate_video(video_id, knowledge_topic_id=10, fanpage_id=10)`
   cho từng video trong 10 video trên → 10 bản copy tên "… (copy)"
   thuộc nhóm 10, mang logo Page 10, người tạo là NamTC.
2. `render_video` (tool đã có) cho từng bản copy → chờ `get_video`
   báo `mp4_outdated=false` mới sang bước 3 (render chỉ xếp job,
   không chờ MP4). Giọng đọc đã được copy nên render không tốn phí
   ElevenLabs. Nếu "Tự duyệt" đang bật, mỗi bản copy sẽ báo "chờ
   duyệt" (không có giờ kế hoạch): vô hại.
3. Xem bản render (`view_render_frames`), nhất là logo mới, rồi
   `schedule_video(video_id, fanpage_id=10)` cho từng bản copy theo
   đúng thứ tự đăng đã chốt → worker tự xếp vào các khung 08:30 /
   11:30 / 15:30 / 18:00.
   **Chỉ làm bước 3 sau 18:00 ngày 15/11**: worker lấy khung trống
   gần nhất cách hiện tại ≥ 30 phút, nên xếp trước 17:30 thì video
   đầu sẽ đăng 18:00 hôm nay chứ không phải 08:30 ngày 16/11.

## Ngoài phạm vi

- Không thêm khả năng đăng bài trực tiếp / xóa video / đổi tài
  khoản qua MCP (giới hạn hiện tại của kết nối giữ nguyên, trừ 2
  tool trong brief này).
- Không đổi luật fill của worker, không đổi `FILL_LEAD` / `FILL_AHEAD`
  / `SLOT_GAP` / `MAX_ITEMS`.
- Không đổi cửa duyệt của các page khác: thêm vào hàng chờ vẫn yêu
  cầu Page thuộc về người gọi, như route web đang làm.
- Không thêm nút web mới, không sửa giao diện "Nhân bản y hệt".

## Nghiệm thu

Agent nghiệm thu bằng test tự động trên DB test và fake services;
không thao tác gì trên production (AGENTS.md). Phần chạy thật do
chủ sản phẩm làm sau khi merge.

- `list-tools` của MCP có 2 tool mới với schema rõ ràng
  (`duplicate_video` có `knowledge_topic_id` và `fanpage_id` tùy
  chọn, `schedule_video` có `fanpage_id` tùy chọn); test liệt kê
  tool trong `api/tests/test_mcp.py` cập nhật theo.
- Test `duplicate_video`: bản copy tên "… (copy)", đúng nhóm đích,
  cùng số cảnh / layer / sản phẩm với gốc, `mp4_key` trống, người
  tạo là người gọi; với `fanpage_id` thì `options.brand_id` = kênh
  của Page đó và logo bật; gốc mang logo kênh khác + `fanpage_id`
  → `schedule_video` lên Page đích không còn bị lệch logo. Lỗi:
  video không có → 404, gốc không có kịch bản → 409 `no_script`,
  nhóm không có → 404, Page không có → 404, Page chưa gắn kênh →
  409, kênh của người khác → 403, kênh chưa có logo → 400; lỗi thì
  không để lại bản copy.
- Test `schedule_video`: đủ điều kiện → có queue item đúng dạng
  `_item_payload`; chưa render → 409 `not_queueable` với đúng lý do
  "Video chưa có MP4" / "MP4 chưa cập nhật"; đã trong hàng chờ →
  409 `already_queued`; `fanpage_id` không phải Page của người gọi
  → 403; kết nối chỉ có quyền đọc → bị từ chối. Fill xếp item vào
  khung trống tiếp theo trong `post_times` của Page.
- Docs cập nhật trong cùng PR: danh sách tool MCP
  (`docs/architecture.md`, `docs/chatgpt.md`), file quyết định mới.
- Lint/format (`ruff check`, `ruff format`) và các test thêm/sửa
  chạy ở máy; bộ đầy đủ để CI chạy. Báo cáo 3 phần theo AGENTS.md.
- Chạy thật (chủ sản phẩm, sau merge): nhân bản thử 1 video với
  `knowledge_topic_id=10, fanpage_id=10`, render, xem logo Page 10
  trên MP4, rồi mới làm cả 10.
