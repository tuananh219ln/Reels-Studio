# Brief: Cắt clip trong kho thành file mới (trim clip to library) — BẢN SỬA

## Bối cảnh
- 16/11/2026 user chốt luật kho mới cho Reels Studio: chỉ giữ file đã qua edit (cắt đúng đoạn cảnh cần), đánh tag phù hợp, KHÔNG giữ video gốc.
- Hiện tại: job dựng 16:00 tải clip TikTok/YouTube về kho rồi gắn vào cảnh. Khi gắn, tool tạo bản sao riêng cho cảnh (`use_in_scene` → `_attach_clip`, copy file vào key `clip-<scene.id>`, render đọc `scene.video_key`) — nên file gốc trong kho thành thừa. Job 16:00 đã được sửa (16/11) để cuối buổi liệt kê file thừa cần xóa, nhưng MCP chưa có lệnh xóa file kho, và cũng chưa có lệnh cắt clip thành file mới.
- Vì vậy kho vẫn chỉ có 2 lựa chọn: giữ nguyên file gốc dài, hoặc xóa hẳn. Không có cách nào giữ lại đúng đoạn đã cắt dưới dạng file trong kho, có tag, để dùng lại cho cảnh khác/video khác.

## Mục tiêu
Thêm khả năng cắt một clip trong kho thành file mới trong kho (đúng đoạn cần dùng), có tag + thư mục, để:
- Kho chỉ giữ file đã qua edit (đúng đoạn cảnh cần), đúng luật kho 16/11.
- File đã cắt gắn được vào cảnh bằng `set_scene_media_from_library` (video_start=0), render bình thường.
- File gốc vẫn còn cho tới khi xóa riêng (không tự xóa).

## Hiện trạng code (đã đọc lại và đối chiếu 16/11 — bản clone 13/11 + main)
- `api/src/reels_api/clips.py`:
  - `MAX_CLIP_SECONDS = 60`.
  - `first_part(path, folder)`: clip lấy từ link (TikTok thường dài hơn 1 phút) chỉ giữ phút đầu (`MAX_CLIP_SECONDS`), không re-encode; clip ngắn hơn thì giữ nguyên.
  - `cut_part(path, sample, start, length, target, *, sound=False)`: cắt `length` giây từ `start`, xuất MP4 H.264, cạnh ngắn nâng lên MIN_SHORT_SIDE nếu nhỏ hơn, re-encode (không copy) vì copy chỉ cắt được ở keyframe; mặc định không có tiếng, trừ khi sound=True. Đã dùng ở 3 chỗ: `footage.py`, `auto_footage.py`, `reference.py` — dùng lại được ngay, không cần sửa hàm.
  - `check_clip(path)`: kiểm tra clip hợp lệ; `probe_sample(path)` / `_probe`: lấy Sample (seconds...).
- `api/src/reels_api/routes_media.py`:
  - `_add`: khi thêm clip vào kho, gọi `first_part` rồi mới lưu — nên clip trong kho TỐI ĐA 60 giây (chỉ phút đầu của video gốc). Đoạn cần dùng nằm sau phút đầu thì file gốc trong kho KHÔNG còn đoạn đó.
  - `use_in_scene(db, storage, media_id, scene_id)`: "bản sao riêng" — copy file kho sang key `clip-<scene.id>` rồi `_attach_clip`; `scene.video_key` trỏ vào bản copy; render đọc `scene.video_key` (jobs.py `copy_to` + `storage.exists`).
  - ĐÃ CÓ route xóa media: `DELETE /api/media/{id}` (`delete_media`) — `ensure_owner(item.created_by_id, me.user_id, "tư liệu này")`: chỉ người đã thêm file mới xóa được; xóa cả DB row + file storage.
  - Chưa có route cắt media.
  - Media item có storage_key, source_url, tags, folder (`list_media` trả source_url, tags...).
- `api/src/reels_api/mcp_server.py`: có `set_scene_media_from_library`, `set_scene_media_from_link`, `list_media`, `view_media`, `add_media_from_links` — chưa có lệnh cắt clip hay xóa media.

## Đề xuất

### 1. Lệnh MCP mới: `cut_clip_to_library`
- Tham số: `media_id` (clip gốc trong kho), `start` (giây bắt đầu, số), `length` (độ dài đoạn, giây), `folder` (thư mục đích, VD "Ăn Lành/16-11"), `tags` (danh sách thẻ, theo chuẩn tag kho: video + cảnh + món/chủ đề, VD ["189-canh1-trung-la-dinh-lang"]), `name` (tên file mới, tùy chọn).
- Hành vi:
  - Kiểm tra file gốc còn trên server (`storage.exists`) — mất thì báo lỗi `media_not_found`, không bịa.
  - Probe file gốc lấy Sample, gọi `cut_part` với sound=False (clip cảnh mặc định không tiếng; lời đọc là giọng riêng) — nếu đoạn cắt không qua được `check_clip` thì báo lỗi, không tạo file rác.
  - GIỚI HẠN (do `_add` chỉ giữ phút đầu): chỉ cắt được đoạn nằm trong 60 giây đầu của clip trong kho; `start + length` vượt quá độ dài file trong kho thì báo lỗi rõ, không tạo file rác.
  - Lưu file cắt thành media item MỚI trong kho (folder + tags như tham số; source_url giữ lại nguồn gốc của file gốc, VD link TikTok, để truy vết).
  - Trả về media_id mới (+ seconds, folder, tags) để job gọi tiếp `set_scene_media_from_library`.
  - KHÔNG xóa file gốc (xóa là bước riêng, dùng lệnh `delete_media` dưới đây).
- Tên lệnh đề xuất: `cut_clip_to_library` (tên khác cũng được, miễn nhất quán trong MCP + web).

### 2. Lệnh MCP mới: `delete_media` (nhỏ — chỉ bọc route đã có)
- Tham số: `media_id`.
- Hành vi: gọi `DELETE /api/media/{id}` đã có sẵn; chỉ người đã thêm file mới xóa được (`ensure_owner`) — xóa file của người khác thì báo lỗi quyền, không xóa lén.
- Hệ quả cho job 16:00: job chạy bằng tài khoản user nên chỉ xóa được file do user (job) tải lên; file do người khác tải thì job chỉ liệt kê, không xóa được — mục "FILE KHO THỪA — CẦN XÓA" trong báo cáo cần ghi rõ file nào xóa được, file nào không.

### 3. (Tùy chọn, cùng đợt hoặc đợt sau) Nút trên web: "Cắt thành file mới trong kho"
- Trên trang chi tiết media item (clip): nhập start + length + thư mục + thẻ → tạo file mới như trên.
- Không bắt buộc cho job chạy, nhưng giúp user cắt tay khi cần.

### 4. Quy tắc
- File cắt phải qua `check_clip` như mọi clip gắn cảnh.
- Đoạn cắt phải nằm trong 60 giây đầu của file trong kho.
- Tag bắt buộc: đủ video + cảnh + món/chủ đề; không để file không tag trong kho.
- Không tự xóa file gốc, không tự gắn file cắt vào cảnh (job/user quyết sau).
- Không đổi đường render hiện tại (cảnh vẫn đọc `scene.video_key`), không đổi `use_in_scene`.

## Tiêu chí nghiệm thu
1. Cắt clip TikTok 60s ở start=20s, length=5s → file mới ~5s trong kho, đúng folder + tags, source_url giữ nguồn gốc. (Vẫn đạt.)
2. File mới gắn vào cảnh bằng `set_scene_media_from_library` (video_start=0) → render ra MP4 đúng đoạn, QC đạt.
3. File gốc vẫn còn nguyên sau khi cắt (chưa xóa).
4. Cắt đoạn không hợp lệ (`start + length` vượt quá độ dài file trong kho, file gốc mất) → báo lỗi rõ, không tạo file rác.
5. `delete_media` xóa được file do chính mình thêm; xóa file của người khác → báo lỗi quyền, file còn nguyên.
6. Job 16:00 dùng được lệnh mới trong Điều 10 (thay bước "tải clip rồi gắn nguyên file" bằng "cắt đoạn cần dùng thành file mới rồi gắn", và xóa file thừa bằng `delete_media` khi đúng chủ) — cập nhật thân job sau khi tool xong (không nằm trong brief này).

## Ngoài phạm vi
- Tự động cắt + gắn + xóa trong một lệnh (giữ từng bước riêng để kiểm chứng được).
- Đổi đường render / `use_in_scene` / footage flow.
- Đổi giới hạn 60s của `_add`/`first_part` (nếu cần đoạn sau phút đầu thì brief riêng).

## Người làm / ghi chú
- Người viết brief: Friday (Muse), 16/11/2026; BẢN SỬA 16/11 sau khi Nam đối chiếu code và chỉ ra 3 sai sót (route xóa đã có, giới hạn 60s, `cut_part` dùng ở 3 chỗ). Cảm ơn Nam đã bắt lỗi.
- Người triển khai: đội Reels Studio (Looper / T3 / Claude) — kiểm lại code trên main trước khi code.
- File liên quan: `api/src/reels_api/clips.py` (`MAX_CLIP_SECONDS`, `first_part`, `cut_part`, `check_clip`), `routes_media.py` (`_add`, `use_in_scene`, `delete_media`), `mcp_server.py` (2 tool mới), `jobs.py` (render đọc `scene.video_key` — không đổi).
