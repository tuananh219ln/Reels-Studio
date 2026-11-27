# Brief: QC và tiêu đề theo nhóm + thông tin gốc gác video

Ngày: 2026-11-26. Người yêu cầu: NamTC (chủ tool). Người viết: Muse (chat Topic Threads).
Bối cảnh: review gate PR #362 (deploy 26/11) + phân tích QC ngày 26/11 + phác họa UI video 444.
Ba việc gộp trong một brief vì cùng chạm vào một chỗ: trang chi tiết video và hàm kiểm tra của gate.

## 1. Vấn đề

### 1.1 Gate áp một chuẩn duy nhất cho mọi format

Tool phục vụ nhiều nhóm với format khác nhau, nhưng toàn bộ ngưỡng QC là hằng số toàn cục:

- `api/src/reels_api/review.py`, `qc_report`: video thường bị chặn `TITLE_EMPTY` khi
  `title_of(video, title)` rỗng. `title_of` (`api/src/reels_api/videos.py`) chỉ đọc
  `plain_title(title.text)` — tức chữ trên màn hình của cảnh tiêu đề. (Video upload
  `mode == "upload"` thì kiểm `video.name`, không liên quan.)
- Format Threads (luật đã chốt 14/11): cảnh tiêu đề KHÔNG có chữ (`text=""` luôn), vì tiêu đề
  đã nằm trong thẻ OP. Nên **mọi video Threads dựng đúng format đều không bao giờ qua được
  TITLE_EMPTY** — không phải thiếu bước, mà là mâu thuẫn cấu trúc. Cách duy nhất qua gate trên
  web hiện tại là gõ tiêu đề lên cảnh tiêu đề, tức phá format Threads.
- `api/src/reels_api/script_rules.py`: `SCENE_COUNT_RANGE = (5, 7)`,
  `TOTAL_SECONDS_RANGE = (20, 55)`; chú thích trong code: "A narrated script at its 150-word
  limit runs about 52 seconds" — giả định kịch bản sức khỏe ~150 từ. Threads: OP + 5–10
  comment ≈ 200–330 từ → 60–96 giây, 9–13 cảnh. `check_script` không có tham số nhóm/format nào.
- `api/src/reels_api/qc.py`: `SHORT, LONG, TOO_SHORT = 20.0, 40.0, 5.0  # the channel's
  20–40 s` — một chuẩn duy nhất cho MP4. Video Threads (60–96 giây) và video sức khỏe dài
  trên 40 giây đều dính warn "kênh nhắm 20–40 giây".

Bằng chứng live ngày 26/11 (lô ngày 15, video 443–448, kiểm bằng MCP `get_video`): 445–448
bị chặn `TITLE_EMPTY`; 443–444 đã được đặt tiêu đề tay trên web thì hết `TITLE_EMPTY` nhưng
lại bị chặn `RENDER_OUTDATED` (đổi tiêu đề sau render làm MP4 thành bản cũ); mọi video mang
2–4 warns độ dài/số cảnh giống hệt nhau mỗi ngày → "Vẫn duyệt" thành nghi thức bấm cho qua,
warn mất tác dụng cảnh báo thật.

Nhóm khác không dính blocker tiêu đề (Ăn Lành, Già, FoodDose có chữ tiêu đề trên màn hình;
Ăn Ngon clone giữ chữ gốc), nhưng video sức khỏe dài trên 55 giây vẫn dính warn độ dài.

### 1.2 Ô tiêu đề chỉ cho chọn, không cho nhập tay, không cho chọn "không tiêu đề"

Hiện tại (`web/src/app/(app)/videos/[id]/page.tsx`, Card `data-testid="title-options"`):
chỉ một `Radio.Group` chọn 1 trong các gợi ý (`title_options`) để chép vào chữ cảnh tiêu đề
(quy tắc trong `docs/specs/web-video-render/user-spec.md`: chọn thì chép vào chữ cảnh tiêu đề;
thành viên sửa tiếp chữ cảnh tiêu đề thì không đổi 5 tiêu đề ứng viên; mọi quy tắc về tiêu đề
áp cho chữ cảnh tiêu đề). Không có ô nhập tay, không có lựa chọn "không dùng tiêu đề".
MCP cũng không có tool nào đặt tiêu đề (`update_video` không có trường title) — chỉ web làm được.

Quyết định của chủ tool ngày 26/11: nới lỏng ô tiêu đề — cho nhập tay, và cho chọn không tiêu đề.

### 1.3 Header không nói video được làm như thế nào

Trang chi tiết video hiện chỉ có trạng thái (Kịch bản / Ảnh / Render / Đăng / Affiliate / QC),
không có thông tin gốc gác: ai làm, làm bằng gì, giọng từ đâu, mất bao lâu. Chủ tool yêu cầu
thêm khối này, lấy video 444 làm mẫu. Phác họa:
`~/workspace/reels-studio/trend-cards/sketch-video-detail-header.html`.

## 2. Đề xuất A — Cấu hình QC theo nhóm (phần chính)

Làm đúng theo tiền lệ `youtube_meta` (quyết định `docs/decisions/2026-11-25-youtube-description.md`):
không viết ngưỡng theo nhóm bằng dict trong code (cách đó đã bị bác trong quyết định YouTube vì
"mọi thay đổi câu chữ đều cần deploy"), mà lưu setting theo nhóm trong DB, sửa được trên tool + MCP.

- Thêm cột JSONB `knowledge_topics.qc_config` (migration mới, theo mẫu migration 0126 của
  `youtube_meta`) + module mới `api/src/reels_api/qc_config.py` theo đúng hình của
  `api/src/reels_api/youtube_meta.py`: `of()` / `clean()` (kiểm tra từng trường, không đặt gì
  thì lưu None) / `is_set()`. Nhóm chưa đặt gì → hành vi cũ, không đổi gì.
- Các trường:
  - `title_required` (bool, mặc định true): false → `qc_report` bỏ qua `TITLE_EMPTY`; tiêu đề
    hiển thị của video lúc đó là `topic` (danh sách + trang chi tiết hiện topic), KHÔNG chép thêm
    chữ nào lên cảnh tiêu đề. Khi `title_required=false`, các kiểm tra chữ tiêu đề khác (số từ
    tối đa) cũng bỏ qua — chữ tiêu đề của nhóm này vốn phải trống.
  - `total_seconds` {min, max} (mặc định 20–55): khoảng warn độ dài tổng, thay `TOTAL_SECONDS_RANGE`
    của nhóm đó. Cap cứng `MAX_TOTAL_SECONDS = 150` giữ nguyên toàn cục.
  - `scene_count` {min, max} (mặc định 5–7): khoảng warn số cảnh nội dung, thay `SCENE_COUNT_RANGE`.
  - `channel_seconds` {min, max} (mặc định 20–40): khoảng warn độ dài MP4, thay `SHORT`/`LONG`
    trong `qc.py` theo nhóm.
  - `short_clip_warn` (bool, mặc định true): false → tắt warn "Video ngắn hơn cảnh, khung cuối sẽ
    đứng yên" của nhóm đó (nền gameplay lặp thì cảnh báo này chỉ là nhiễu).
  - Âm lượng GIỮ NGUYÊN toàn cục (`TARGET_LUFS = -14`, chuẩn nền tảng TikTok/Reels/Shorts) —
    cố tình KHÔNG cho cấu hình theo nhóm.
- Nối dây: `check_script` / `run_checks` / `qc_report` / `qc.check_format` nhận config của nhóm
  (qua video → knowledge_topic). Ngoài nhánh `TITLE_EMPTY`, `RENDER_OUTDATED` và các chặn khác
  giữ nguyên.
- Giao diện sửa: cùng chỗ với `youtube_meta` (Kho kiến thức › Cài đặt nhóm › mục QC & duyệt) +
  MCP `get_qc_config` / `update_qc_config` (theo mẫu `get_youtube_meta` / `update_youtube_meta`).
- Giá trị seed ban đầu (chủ tool chốt từ số liệu thật):
  - Threads (nhóm 9): `title_required=false`; `total_seconds` 45–100; `scene_count` 5–13;
    `channel_seconds` 60–90; `short_clip_warn=false`.
  - Ăn Lành (nhóm 7), Già (nhóm 6): giữ nguyên hiện tại (true; 20–55; 5–7; 20–40; true).
  - FoodDose (nhóm 12), Ăn Ngon (nhóm 10): để trống (hành vi cũ) cho tới khi chủ nhóm đặt.
- Kèm decision doc `docs/decisions/2026-11-26-per-group-qc.md` (theo mẫu quyết định YouTube 25/11).

## 3. Ô tiêu đề nới lỏng (cùng trang video, Card title-options)

- Giữ `Radio.Group` gợi ý như cũ; thêm ô text nhập tay — ghi thẳng vào chữ cảnh tiêu đề (cùng
  trường mà picker đang ghi; sửa chữ không đổi `title_options`, theo user-spec.md).
- Thêm tick "Không dùng tiêu đề": tick thì xóa chữ cảnh tiêu đề VÀ ghi một cờ per-video (đề xuất
  tên `videos.no_title`, coder chốt tên cuối) để gate bỏ qua `TITLE_EMPTY` cho video đó ngay cả
  khi nhóm bắt tiêu đề. Bỏ tick thì khôi phục chữ đã lưu trước đó (giữ lại, không xóa hẳn) hoặc
  để trống cho nhập tay. Trường hợp video đã có chữ tiêu đề từ trước (VD video Threads bị đặt
  tiêu đề tay), tick mục này phải xóa sạch chữ cảnh tiêu đề — chữ cũ còn sót sẽ bị vẽ đè lên thẻ
  khi render lại (đã xảy ra với video 443 ngày 26/11: chữ tiêu đề 13 từ đè lên thẻ OP và dòng hook,
  khung hình kiểm chứng lúc 21:36).
- Dưới ô hiện dòng xem trước: "Trên màn hình sẽ hiện: …" / "Không có chữ tiêu đề". Đổi tiêu đề
  sau khi render thì MP4 thành bản cũ — hành vi này đã có, giữ nguyên.
- MCP: thêm tool đặt tiêu đề (nhập tay | chọn từ `title_options` | không tiêu đề) để Muse làm
  được việc này mà không cần web. Đây là lỗ hổng phát hiện ngày 26/11: `update_video` không có
  trường title, `set_video_options` cũng không.

## 4. Header: khối "Video này được làm như thế nào" (cùng trang video, dưới thanh trạng thái)

Thẻ mới, gấp/mở được. Toàn bộ dữ liệu đã có sẵn trong backend — không thu thập thêm gì mới:

- Tạo bởi: `created_by` + `created_at` + kênh tạo (Muse qua MCP / web tay / tự viết) +
  `assistant_app` (Muse/ChatGPT/…) + ghi chú "gói đăng ký, không tốn phí AI của nhóm" (câu này
  trang hiện đã tính sẵn cho ghi chú dưới ô tiêu đề — dùng lại).
- Kịch bản: nguồn kịch bản (Muse viết qua MCP / thành viên tự viết / `hand_written`), thẻ tự dựng
  hay làm tay.
- Giọng đọc: tóm tắt theo video + chip theo từng cảnh trong danh sách cảnh — `voice_id` + nguồn
  (VieNeu / Muse TTS / ElevenLabs / Gemini) + `voice_custom` (file MP3 tải lên) + kết quả loudnorm
  nếu có; lô trộn 2 nguồn giọng thì gắn nhãn cảnh báo.
- Nhạc: `music_track_id` + volume; Nền: clip; Nhóm / format / vibe.
- Thời gian: `created_at` → `rendered_at` (tổng thời gian làm), thời gian render (job render),
  lần sửa cuối + lý do MP4 thành bản cũ (nếu có).
- Đóng góp: ai làm gì (Muse: kịch bản + thẻ + giọng; thành viên: chọn chủ đề, duyệt).
- Timeline: Tạo → Kịch bản → Gắn giọng → Render → (Sửa) → Duyệt, lấy từ `video_events`
  (quyết định gate ghi "Every step is a video_events row") + bản ghi job render.
- Nút "Sao chép hồ sơ video" — copy toàn bộ khối trên dạng text để dán vào báo cáo/chat.

Ca kiểm thử: video 444 phải hiện đúng số thật — NamTC 17:37 qua Muse (MCP); giọng VieNeu xoay
(Quân Kể Chuyện, Lan Chi, …); tạo 17:37 → render xong 18:36 (59 phút), render ~6 phút;
21:08 đặt tiêu đề (NamTC, trên web).

## 5. Giai đoạn 2 (tùy chọn, không chặn mục 2–4)

- Tab lịch sử thay đổi của video (đọc `video_events`: ai sửa gì, lúc nào — trả lời ngay câu
  "vì sao video báo cần render lại").
- Cảnh báo trộn nguồn giọng trong một lô (lô ngày 15: 5 VieNeu + 1 Muse).
- Lọc video theo nguồn giọng ở danh sách video (đổi hàng loạt video còn VieNeu sang giọng Muse).
- Người duyệt + giờ duyệt + kênh duyệt (web/MCP) hiện ngay trên header sau khi duyệt.
- So sánh nhanh với video gốc (video clone hoặc tái dùng chủ đề: link video gốc + điểm khác).
- Mỗi cảnh báo QC hiện kèm ngưỡng của nhóm đó, ví dụ "96 giây (nhóm Threads cho phép tới 100 giây)".

## 6. Tiêu chí nghiệm thu

- [ ] Video Threads mới (không chữ tiêu đề, 60–96 giây, 9–13 cảnh) qua được gate khi chỉ còn
  warns đã acknowledge — không còn `TITLE_EMPTY`, không còn warns độ dài/số cảnh khi nằm trong
  ngưỡng nhóm.
- [ ] Video sức khỏe giữ nguyên hành vi cũ (bắt tiêu đề; ngưỡng 20–55 giây, 5–7 cảnh, 20–40 giây).
- [ ] Nhóm chưa đặt `qc_config` → hành vi cũ, không đổi gì.
- [ ] Trên trang video: nhập tay tiêu đề lưu được; tick "Không dùng tiêu đề" thì duyệt được video
  của nhóm bắt tiêu đề (nhờ cờ per-video); bỏ tick khôi phục chữ cũ.
- [ ] Khối provenance hiện đúng dữ liệu thật của video 444 (kiểm bằng mắt trên trang).
- [ ] MCP: Muse đặt được tiêu đề (nhập tay / chọn gợi ý / không tiêu đề) mà không cần web.
- [ ] Không đổi hành vi đăng (schedule/post routes, auto-post) và không đổi ngưỡng âm lượng.
- [ ] Có migration + decision doc; deploy xong báo lại để kiểm chứng live (như tiền lệ youtube_meta).

## 7. Ngoài phạm vi

- Không đổi format video, giọng, nhạc, render; không đổi luồng duyệt (`approve_video`);
  không bật tự duyệt.
- Không xử lý lô ngày 15 (443–448) bằng code: lô này xử lý tay — đặt tiêu đề → render lại
  443/444 → duyệt cả 6 (chủ tool quyết riêng).

## 8. Tài liệu tham khảo

- Phân tích QC: `~/workspace/reels-studio/trend-cards/qc-gate-analysis-2026-11-26.md`
- Phác họa UI: `~/workspace/reels-studio/trend-cards/sketch-video-detail-header.html`
- Quyết định gate: `docs/decisions/2026-11-26-review-gate.md`; tiền lệ youtube_meta:
  `docs/decisions/2026-11-25-youtube-description.md`, `api/src/reels_api/youtube_meta.py`,
  migration 0126.
- Code liên quan: `api/src/reels_api/review.py` (`qc_report`), `videos.py` (`title_of`,
  `run_checks`, `split_scenes`), `script_rules.py` (`SCENE_COUNT_RANGE`, `TOTAL_SECONDS_RANGE`),
  `qc.py` (`SHORT`, `LONG`, `TARGET_LUFS`), `web/src/app/(app)/videos/[id]/page.tsx`
  (Card `title-options`), `docs/specs/web-video-render/user-spec.md` (quy tắc tiêu đề).
