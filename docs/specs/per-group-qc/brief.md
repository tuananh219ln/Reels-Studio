# Brief: QC và tiêu đề theo nhóm + thông tin gốc gác video

Ngày: 2026-11-26. Người yêu cầu: NamTC (chủ tool). Người viết: Muse (chat Topic Threads); sửa sau review cùng ngày
(đối chiếu `main` f0aebfd và danh sách nhóm thật qua MCP). Bối cảnh: review gate PR #362 (deploy 26/11) + phân tích
QC ngày 26/11 + phác họa UI video 444. Ba việc gộp trong **một PR** (chủ tool chốt 26/11) vì cùng chạm vào một chỗ:
trang chi tiết video và hàm kiểm tra của gate.

## 1. Vấn đề

### 1.1 Gate áp một chuẩn duy nhất cho mọi format

Tool phục vụ nhiều nhóm với format khác nhau, nhưng toàn bộ ngưỡng QC là hằng số toàn cục:

- `api/src/reels_api/review.py`, `qc_report`: video thường bị chặn `TITLE_EMPTY` khi
  `title_of(video, title)` rỗng. `title_of` (`api/src/reels_api/videos.py`) chỉ đọc
  `plain_title(title.text)` — tức chữ trên màn hình của cảnh tiêu đề. (Video upload
  `mode == "upload"` thì kiểm `video.name`, không liên quan.)
- Format Threads (luật đã chốt 14/11): cảnh tiêu đề KHÔNG có chữ (`text=""` luôn), vì tiêu đề
  đã nằm trong thẻ OP. Nên **mọi video Threads dựng đúng format đều không bao giờ qua được
  TITLE_EMPTY** — không phải thiếu bước, mà là mâu thuẫn cấu trúc.
- `api/src/reels_api/script_rules.py`: `SCENE_COUNT_RANGE = (5, 7)`,
  `TOTAL_SECONDS_RANGE = (20, 55)`; giả định kịch bản sức khỏe ~150 từ. Threads: OP + 5–10
  comment ≈ 200–330 từ → 60–96 giây, 9–13 cảnh. `check_script` không có tham số nhóm/format nào.
- `api/src/reels_api/qc.py`: `SHORT, LONG = 20.0, 40.0` — một chuẩn duy nhất cho MP4. **Lời cảnh báo
  "kênh nhắm 20–40 giây" được chấm lúc render và lưu cứng vào `videos.qc`**, nên đổi ngưỡng ở `check_format` không
  chạm tới video đã render.

Bằng chứng live ngày 26/11 (lô ngày 15, video 443–448): 445–448 bị chặn `TITLE_EMPTY`; 443–444 đặt tiêu đề tay thì
lại bị chặn `RENDER_OUTDATED`; mọi video mang 2–4 warns độ dài/số cảnh giống hệt nhau mỗi ngày → "Vẫn duyệt" thành
nghi thức bấm cho qua.

### 1.2 Ô tiêu đề chỉ cho chọn gợi ý, không có "không tiêu đề"

Card `data-testid="title-options"` (`web/src/app/(app)/videos/[id]/page.tsx`) chỉ có `Radio.Group` chép gợi ý vào
chữ cảnh tiêu đề (quy tắc ở `docs/specs/web-video-render/user-spec.md`). Chữ cảnh tiêu đề **đã sửa tay được** trong
danh sách cảnh, và MCP `update_scene` **đã sửa được** chữ cảnh tiêu đề (`shuffle_duplicate_video` dặn Muse làm vậy).
Thứ thật sự thiếu: lựa chọn "không dùng tiêu đề" (web và MCP), và một lối tắt nhập tay ngay ở ô tiêu đề.

Quyết định của chủ tool ngày 26/11: nới lỏng ô tiêu đề — cho nhập tay, và cho chọn không tiêu đề.

### 1.3 Header không nói video được làm như thế nào; sửa video không để lại dấu vết

Trang chi tiết video không có thông tin gốc gác: ai làm, làm bằng gì, giọng từ đâu, mất bao lâu. `video_events` chỉ
ghi các bước **duyệt** (review_requested, approved, rejected, restored, publish_skipped, uploaded, mp4_replaced);
`edit_logs` chưa theo dõi video. Không có chỗ nào ghi "ai sửa tiêu đề lúc nào", nên không trả lời được câu "vì sao
video báo cần render lại". Chủ tool chốt 26/11: **thêm việc ghi sự kiện sửa video** trong cùng PR, và có hoàn tác.

### 1.4 Thông tin giọng không đồng bộ

Chuẩn giọng Topic Threads hiện tại (chủ tool xác nhận 26/11) là **Muse theo vai + VieNeu**, nhưng cài đặt "Giọng đọc
theo vai" của nhóm 9 trên tool vẫn ghi ElevenLabs Chi/Adam + Gemini — vì MCP không sửa được mục này và chưa ai sửa
trên web. Nguồn đúng duy nhất là cài đặt nhóm trên tool; brief và ghi nhớ chỉ trỏ tới nó.

## 2. Phần A — Cấu hình QC theo nhóm

Theo tiền lệ `youtube_meta` (`docs/decisions/2026-11-25-youtube-description.md`): setting theo nhóm trong DB, sửa được
trên tool + MCP, không dùng dict trong code.

- Cột JSONB `knowledge_topics.qc_config` (migration mới) + module `api/src/reels_api/qc_config.py` theo hình
  `youtube_meta.py`: `of()` (đủ trường, mặc định = hành vi cũ) / `clean()` (kiểm từng trường; trùng hết mặc định thì
  lưu None) / `is_set()`. Nhóm để trống (None) → hành vi cũ, không đổi gì.
- Các trường:
  - `title_required` (bool, mặc định true): false → `qc_report` bỏ qua `TITLE_EMPTY`; danh sách hiện `topic` khi
    không có tiêu đề (đã có sẵn: `video_name` lấy name → tiêu đề → topic).
  - `total_seconds` {min, max} (mặc định 20–55): khoảng warn độ dài tổng. Cap cứng `MAX_TOTAL_SECONDS = 150` giữ
    nguyên toàn cục.
  - `scene_count` {min, max} (mặc định 5–7): khoảng warn số cảnh nội dung.
  - `channel_seconds` {min, max} (mặc định 20–40): khoảng warn độ dài MP4. **Chấm lại lúc đọc** từ
    `videos.mp4_seconds` (thay mục "Độ dài" đã lưu trong `videos.qc`), để video đã render cũng theo ngưỡng mới.
  - ~~`short_clip_warn`~~ **bỏ**: cảnh báo "Video ngắn hơn cảnh" đã tự tắt khi cảnh bật "Lặp clip"
    (`scenes.video_loop`); khi nó hiện thì khung cuối đứng yên thật. Thay vào đó MCP `update_scene` nhận thêm
    `video_loop` để Muse bật lặp cho nền gameplay.
  - Âm lượng GIỮ NGUYÊN toàn cục (−14 LUFS) — cố tình không cho cấu hình theo nhóm.
- Nối dây: `check_script` nhận khoảng độ dài/số cảnh; `run_checks` lấy theo nhóm của video; `qc_report` đọc
  `title_required`, cờ `no_title` của video và `channel_seconds`. `RENDER_OUTDATED` và các chặn khác giữ nguyên.
- Giao diện: thẻ "QC & duyệt" ở Kho kiến thức › Cài đặt nhóm; MCP `get_qc_config` / `update_qc_config`; theo dõi
  trong Lịch sử nhóm (`TOPIC_FIELDS`); "Nhân bản nhóm" chép theo.
- Seed (dò theo **tên nhóm** như migration 0126, không theo id):
  - "Topic Threads" (id 9): `title_required=false`; `total_seconds` 45–100; `scene_count` 5–13;
    `channel_seconds` 60–90.
  - Còn lại (Già 6, Ăn Lành 7, Nhóm test 10, FoodDose 12, và 1, 11, 13): **để trống** = dùng mặc định trong code,
    đúng hành vi hôm nay; sau này đổi mặc định thì các nhóm này đổi theo.

## 3. Phần B — Ô tiêu đề nới lỏng

- Giữ `Radio.Group` gợi ý; thêm ô nhập tay ghi thẳng vào chữ cảnh tiêu đề (cùng trường picker đang ghi; không đổi
  `title_options`).
- Tick "Không dùng tiêu đề": xóa chữ cảnh tiêu đề, cất chữ cũ vào `videos.kept_title`, bật cờ `videos.no_title` để
  gate bỏ qua `TITLE_EMPTY` dù nhóm bắt tiêu đề. Bỏ tick: trả lại chữ đã cất. Gõ chữ vào cảnh tiêu đề thì cờ tự tắt.
- Dòng xem trước: "Trên màn hình sẽ hiện: …" / "Không có chữ tiêu đề". Đổi tiêu đề sau render thì MP4 thành bản cũ —
  giữ nguyên.
- MCP: tool `set_video_title` (nhập tay | chọn số thứ tự trong `title_options` | không tiêu đề).

## 4. Phần C — Lịch sử sửa video + header "Video này được làm như thế nào"

### 4.1 Ghi sự kiện sửa (mới)

- Mở rộng `edit_logs` (quyết định 2026-11-09 đã ghi "các thứ khác sẽ theo sau") với loại `video`: mỗi lần sửa nội
  dung video (tên, caption, hashtag, dòng khảo sát, bình luận thêm, nhạc, kiểu video, tùy chọn, không tiêu đề) và
  cảnh (chữ, lời đọc, số giây, giọng, từ khóa, lặp clip...) ghi một dòng: ai, kênh (`web` / `mcp`), cũ → mới.
- "Lịch sử sửa" trên trang video, mỗi mục có "Hoàn tác" (ghi lại giá trị cũ thành một lần sửa mới, không xóa gì).
  Hoàn tác bị từ chối nếu sau đó đã có lần sửa khác ở cùng mục (báo xung đột, không đè), hoặc cảnh đã bị xóa.
- Giới hạn: giọng đã tạo và MP4 không hoàn tác được (hoàn tác xong cần render lại như mọi lần sửa); ảnh/clip, thêm/
  xóa/đổi thứ tự cảnh chưa ghi trong PR này. Ctrl+Z để PR sau (đụng mọi ô nhập trên trang).

### 4.2 Header

Thẻ gấp/mở dưới thanh trạng thái, dữ liệu từ backend:

- Tạo bởi: `created_by` + `created_at` + nguồn kịch bản (`written_via`/`assistant_app`: Muse/ChatGPT/… qua MCP,
  `hand_written`, AI của nhóm, nhân bản, video mẫu, MP4 tải lên).
- Giọng đọc: tóm tắt theo nguồn + từng cảnh. Nguồn thật: ElevenLabs (mã), VieNeu (`vieneu:`), Gemini (`gemini:`),
  Google (`google:`), MP3 tải lên (`voice_signature = "custom:…"`, tên file `voice_name`). Không có nguồn "Muse TTS":
  giọng Muse đến dưới dạng MP3 tải lên. Video trộn từ 2 nguồn trở lên thì gắn nhãn.
- Nhạc: `music_name` + `music_volume`; nhóm; kiểu video.
- Thời gian: `created_at` → `rendered_at`, `render_seconds`, lần sửa cuối (từ 4.1).
- Timeline: tạo + các job (kịch bản, giọng, ảnh, render…) + sự kiện duyệt (`video_events`) + lần sửa (4.1).
- Nút "Sao chép hồ sơ video".

Ca kiểm thử: video 444 hiện đúng người tạo, kênh (Muse qua MCP), giọng từng cảnh, giờ tạo → render xong và thời gian
render. **Các lần sửa trước khi PR này deploy (vd. 21:08 đặt tiêu đề) không có trong lịch sử**, vì chưa từng được ghi.

## 5. Phần D — MCP sửa "Giọng đọc theo vai"

- Tool `update_voice_format` (theo mẫu `update_youtube_meta`): dùng `voice_format.clean` và đường sửa nhóm của web;
  chỉ người được sửa nhóm mới sửa được; ghi vào Lịch sử nhóm; tool dặn chỉ sửa khi thành viên yêu cầu rõ.
- Sau deploy, chủ tool nhờ Muse đặt Topic Threads về "Muse theo vai + VieNeu" (PR không tự đổi dữ liệu này vì chưa
  có giọng cụ thể cho từng vai).

## 6. Giai đoạn 2 (không chặn PR này)

- Ctrl+Z trên trang video; ghi cả thay ảnh/clip, thêm/xóa/đổi thứ tự cảnh.
- Cảnh báo trộn nguồn giọng trong một lô; lọc video theo nguồn giọng.
- So sánh nhanh với video gốc (clone/tái dùng chủ đề).
- Mỗi cảnh báo QC hiện kèm ngưỡng nhóm (một phần đã có: lời cảnh báo ghi khoảng của nhóm).

## 7. Tiêu chí nghiệm thu

- [ ] Video Threads (không chữ tiêu đề, 60–96 giây, 9–13 cảnh) qua gate khi chỉ còn warns đã acknowledge — không
  `TITLE_EMPTY`, không warns độ dài/số cảnh khi trong ngưỡng nhóm, kể cả video đã render trước deploy.
- [ ] Nhóm để trống `qc_config` → hành vi cũ y nguyên.
- [ ] Nhập tay tiêu đề lưu được; tick "Không dùng tiêu đề" thì duyệt được video của nhóm bắt tiêu đề; bỏ tick trả
  lại chữ cũ.
- [ ] Sửa video/cảnh trên web hoặc qua MCP hiện trong Lịch sử sửa; Hoàn tác trả lại giá trị cũ, báo xung đột khi đã
  có lần sửa sau.
- [ ] Header hiện đúng dữ liệu thật của video 444 (kiểm bằng mắt sau deploy).
- [ ] MCP: `set_video_title`, `get_qc_config`/`update_qc_config`, `update_voice_format`, `update_scene.video_loop`.
- [ ] Không đổi hành vi đăng và ngưỡng âm lượng; không đổi render.
- [ ] Có migration + decision doc + hướng dẫn trong app; deploy xong kiểm chứng live.

## 8. Ngoài phạm vi

- Không đổi format video, giọng, nhạc, render; không đổi luồng duyệt (`approve_video`); không bật tự duyệt.
- Không xử lý lô ngày 15 (443–448) bằng code: chủ tool xử lý tay.

## 9. Tài liệu tham khảo

- Quyết định: `docs/decisions/2026-11-26-review-gate.md`, `2026-11-20-total-length-150.md` (hai quyết định được nới),
  `2026-11-25-youtube-description.md` (mẫu), `2026-11-09-edit-history.md` (lịch sử sửa).
- Code: `review.py` (`qc_report`), `videos.py` (`title_of`, `run_checks`), `script_rules.py`, `qc.py`,
  `youtube_meta.py`, `voice_format.py`, `edit_log.py`, `web/src/app/(app)/videos/[id]/page.tsx`.
