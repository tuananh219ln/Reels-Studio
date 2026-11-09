# Brief Reels Studio — Vị trí hộp chữ tiêu đề: thêm tuỳ chọn `title_text_position` (đặt được qua API + MCP)

> **Việc MỚI, brief riêng** — user chốt sáng 09/11/2026 sau khi kiểm
> chứng trực tiếp qua MCP trên production (video 64).
>
> Thi công theo lệ team: đọc AGENTS.md + docs/decisions.md và các
> file quyết định riêng trong docs/decisions/ trước; làm trên
> **nhánh mới** `feat/title-text-position` tạo từ main; TDD, test
> bằng fake services, báo cáo 3 phần, **không tự merge**. Quyết
> định phát sinh ghi thành **file riêng trong docs/decisions/**,
> không append vào docs/decisions.md. **Tuyệt đối không dùng
> subagent** (lệ riêng của user — việc chạy inline trong một
> phiên).
>
> Nơi brief thuộc về: `docs/specs/title-text-position/brief.md`
> trong repo. (Bản đang đọc được soạn ngoài repo ngày 09/11 và
> cần được chép vào đúng thư mục đó khi bắt đầu thi công.)

## Vấn đề (kiểm chứng qua MCP trên production, video 64, sáng 09/11/2026)

- `set_video_options` có trường `text_position` [x, y] — "tâm hộp
  chữ các cảnh" trong khung 1080×1920.
- Thử đặt `text_position = [540, 290]`: chữ của cảnh thường
  (cảnh 437) **dời thật** từ dưới lên trên; nhưng hộp chữ vàng của
  **cảnh tiêu đề** (cảnh 436; `title_text_style` "box",
  `title_box_color` #FFD60A, `title_style` "same") **không đổi vị
  trí** — ảnh xem trước của cảnh tiêu đề giống hệt từng byte
  trước/sau khi đặt. Đã trả `text_position` về null.
- Hệ quả thực tế: hộp tiêu đề cố định ở giữa khung và **che mặt
  người** trong ảnh mở đầu mỗi khi mặt nằm giữa khung (đúng ca
  video 64 ngày 09/11). Cách néo hiện tại: chọn ảnh mở đầu có mặt
  nằm ngoài dải giữa khung — phụ thuộc bố cục ảnh, không chủ động
  được.

## Kết quả đọc code (repo tuananh219ln/Reels-Studio, main @ d366ec6, 09/11/2026)

Đường đi API → job → worker đã rõ, điểm nghẽn nằm ở đúng một hàm:

1. **Worker render đã hỗ trợ dời hộp tiêu đề theo chiều dọc** —
   không cần sửa:
   - `worker/src/reels_render/textbox.py`, hàm `place_box(width,
     height, centre, is_title)`: khi `centre is None` thì dùng
     `title_box_position()` = `((FRAME_WIDTH − width)//2,
     (FRAME_HEIGHT − height)//2)` — chính giữa khung 1080×1920
     (đây là "chỗ của mẫu" đang thấy trên production). Khi có
     `centre`: cảnh tiêu đề chỉ dời **dọc** — x luôn căn giữa, y
     được kẹp trong `SAFE_ZONE` (top 220 … `SCENE_BOX_BOTTOM`).
     Test đã khoá: `worker/tests/test_textbox.py` —
     `place_box(400, 200, (100, 500), is_title=True) ==
     ((FRAME_WIDTH − 400)//2, 400)`.
   - `worker/src/reels_render/render.py` (dòng ~117):
     `box_x, box_y = place_box(layout.width, layout.height,
     scene.text_position, is_title=index == 0)`;
     `worker/src/reels_render/script.py` (dòng ~38): trường
     `Scene.text_position` — "the text box's centre in the frame;
     None: the template's place".
2. **API chỉ đưa `text_position` vào kịch bản render khi hàm phân
   giải trả về giá trị:** `api/src/reels_api/jobs.py` (dòng
   ~649–650): `if position := text_position(video, scene):
   data["text_position"] = position`. Cùng hàm phân giải này
   cũng cấp cho xem trước cảnh (`api/src/reels_api/videos.py`
   ~dòng 401), thumbnail (~dòng 464) và style xem trước (~dòng
   760) — sửa một chỗ là render/thumbnail/preview nhất quán.
3. **Điểm nghẽn — `api/src/reels_api/videos.py`, hàm
   `text_position(video, scene)` (dòng 324–331):**

   ```python
   def text_position(video: Video, scene: Scene) -> list[int] | None:
       """Where the scene's text box goes (its centre): its own place, else for a content scene the video's place,
       else None (where the template puts it)."""
       if scene.text_x is not None and scene.text_y is not None:
           return [scene.text_x, scene.text_y]
       if scene.is_title:
           return None
       return effective(video)["text_position"]
   ```

   Cảnh tiêu đề không có vị trí riêng thì hàm trả `None` ngay —
   tuỳ chọn cấp video bị bỏ qua **có chủ đích**: chú thích tại
   `DEFAULTS` trong `api/src/reels_api/video_options.py` (dòng
   ~62) ghi rõ `text_position` cấp video là "The content scenes'
   text box centre in the frame" — chỉ dành cho cảnh thường.
4. **Vị trí riêng của cảnh tiêu đề hiện chỉ đặt được trên web:**
   `PATCH /api/scenes/{id}` (`api/src/reels_api/routes_videos.py`
   ~dòng 1125–1137; với cảnh tiêu đề, x bị ép = `FRAME_WIDTH//2`)
   — chính là thao tác kéo thả trong `TextPositionModal` trên
   web. **MCP không có tool nào đặt `text_position` cho từng
   cảnh**; `set_video_options` (`api/src/reels_api/mcp_server.py`
   ~dòng 969) chỉ có `text_position` cấp video.
5. **Hành vi hiện tại bị khoá bằng test** —
   `api/tests/test_text_position.py` (dòng ~72–74): "The title is
   not a content scene: it keeps its own place (the centre)
   whatever the scenes use", và ~dòng 130: "The title keeps the
   template's place; the first scene its own; the second the
   video's." → Không được phá ngữ nghĩa này.

## Phương án sửa (đề xuất): thêm tuỳ chọn riêng `title_text_position`

Hệ tuỳ chọn đã có họ `title_*` riêng cho cảnh tiêu đề
(`title_text_style`, `title_text_color`, `title_box_color`,
`title_accent_color`, `title_box_opacity`, `title_text_size`,
`title_text_case`) — thêm `title_text_position` là đúng quy ước
sẵn có, **không** đổi ngữ nghĩa `text_position` hiện tại, và mặc
định `None` nên không video cũ nào đổi hành vi.

Điểm chạm tối thiểu:

1. `api/src/reels_api/video_options.py`:
   - `DEFAULTS`: thêm `"title_text_position": None` cạnh
     `text_position`, kèm chú thích: tâm hộp chữ cảnh tiêu đề
     [x, y]; `None`: chỗ của mẫu (chính giữa khung); thành phần x
     không có tác dụng vì tiêu đề luôn căn giữa ngang.
   - `clean()`: xử lý `title_text_position` như `text_position`
     (dùng lại `clean_position`).
   - `choices()`: thêm mục `title_text_position` dạng
     `{"width": FRAME_WIDTH, "height": FRAME_HEIGHT}` như
     `text_position`, để phía kết nối (MCP/web) đọc được.
   - `look_signature()`: thêm `"title_text_position"` vào vòng
     loại trừ cùng kiểu `(*LATER_LOOK_FIELDS, "text_position")`,
     để video chưa dùng tính năng giữ nguyên chữ ký render (MP4
     đã render không bị coi là lỗi thời).
2. `api/src/reels_api/videos.py`, hàm `text_position()`: ở nhánh
   cảnh tiêu đề — sau khi kiểm tra vị trí riêng của cảnh
   (`scene.text_x/text_y`, vẫn thắng) — trả về
   `effective(video)["title_text_position"]` thay cho `None`
   cứng; ép thành phần x = `FRAME_WIDTH // 2` cho khớp hành vi
   hiện tại ở `routes_videos.py` và `place_box`. Cập nhật
   docstring của hàm cho khớp.
3. `api/src/reels_api/mcp_server.py`, tool `set_video_options`:
   thêm tham số `title_text_position` (cùng kiểu và mô tả như
   `title_text_position` của cảnh tiêu đề) và một cơ chế xoá về
   mặc định tương ứng (thêm cờ reset riêng, hoặc mở rộng
   `reset_text_position` cho cả hai trường — người thi công chọn
   một cách, nêu rõ trong báo cáo; yêu cầu tối thiểu: qua MCP
   **đặt được và xoá được** `title_text_position`).
4. Web (không bắt buộc trong brief này, tách PR sau nếu muốn):
   thêm điều khiển trong `web/src/components/video/
   VideoSettings.tsx` cạnh các trường `title_*` khác.

**Không sửa worker** (`place_box` đã hỗ trợ), **không migration
dữ liệu** — tuỳ chọn là JSON và `effective()` hợp nhất `DEFAULTS`
nên video cũ tự có khoá mới = `None` (người thi công kiểm chứng
điểm này khi làm và nêu trong báo cáo).

### Phương án đã cân nhắc và loại

Cho cảnh tiêu đề dùng chung `text_position` cấp video (bỏ dòng
`if scene.is_title: return None`): diff nhỏ nhất, nhưng phá ngữ
nghĩa đã được ghi chú thích + test khoá, và mọi video hiện hữu
đã đặt `text_position` cho cảnh thường sẽ bị hộp tiêu đề nhảy
vị trí âm thầm ở lần render kế tiếp. **Không chọn.**

## Tiêu chí nghiệm thu

1. Qua MCP: `set_video_options(title_text_position=[540, 290])`
   cho một video nháp → render (hoặc xem trước cảnh tiêu đề):
   hộp tiêu đề của cảnh mở đầu nằm ở vùng trên khung (tâm ~y 290,
   bị kẹp trong `SAFE_ZONE`), không che mặt; chữ các cảnh thường
   giữ nguyên vị trí.
2. Không đặt `title_text_position` (`None`) → render giống hệt
   hiện tại (hộp tiêu đề giữa khung) — kể cả với video đã đặt
   `text_position` cấp video cho cảnh thường.
3. Vị trí riêng của cảnh tiêu đề (kéo trên web) vẫn thắng
   `title_text_position`.
4. Đặt qua REST (PATCH tuỳ chọn video) và qua MCP cho cùng kết
   quả; giá trị sai (ngoài khung, sai kiểu) bị từ chối và không
   lưu gì, như `text_position` hiện tại.
5. Test: thêm test theo kiểu `api/tests/test_text_position.py`
   cho nhánh tiêu đề (hàm phân giải + MCP đặt/reset); toàn bộ
   test cũ về `text_position` vẫn xanh nguyên vẹn; test worker
   không phải sửa.
6. Video chưa từng đặt `title_text_position` không bị đổi
   `look_signature`.

## Ngoài phạm vi / ghi chú

- Đây là **cải tiến tool, không chặn việc đăng bài hiện tại**:
  trong lúc chờ sửa, vẫn néo được bằng cách chọn ảnh mở đầu có
  mặt nằm ngoài dải giữa khung (đang áp dụng cho video 64).
- Không đổi vị trí mặc định của mẫu, không đổi hành vi
  `text_position` hiện tại, không đụng caption (caption bám theo
  hộp chữ của cảnh thường; cảnh tiêu đề không có caption).
