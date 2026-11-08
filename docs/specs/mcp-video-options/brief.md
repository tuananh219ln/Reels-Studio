# Brief Reels Studio — Thêm tool MCP chỉnh tùy chọn video (giọng đọc + cỡ chữ tiêu đề)

> Soạn 08/11/2026 theo quyết định của user (chủ sản phẩm).
> Cách làm theo lệ của team: đọc AGENTS.md + docs/decisions.md trước;
> nhánh riêng; TDD (viết test trước); chạy đủ test api + web; báo cáo
> 3 phần theo AGENTS.md; không tự merge; chạy inline, không dùng
> subagent.

## Bối cảnh (đã kiểm chứng 08/11)

Server MCP của app hiện có 39 tool. Các tool ghi gần nhất là
`set_audio` (chọn nhạc nền, âm lượng nhạc, bật/tắt giọng đọc
ElevenLabs) và `update_video` (caption, hashtag, bình luận ghim) —
nhưng **không có tool nào ghi được bộ tùy chọn dựng của một video**
(trường `options` mà `get_video` trả về: `voice_id`, `title_text_size`,
`text_size`, `transition`, `motion`, `zoom`, `captions`, các màu
kiểu chữ...). Muốn đổi các giá trị đó qua MCP là không thể; chỉ làm
được trên web, ở tab "Thiết lập" của từng video.

Hệ quả thực tế đã gặp 2 lần trong ngày 08/11 (video 60 và video 61):

1. Video mới luôn kế thừa mặc định của team: giọng VieNeu
   "Huyền My". Chuẩn giọng của page Ăn Lành Sống Khỏe là ElevenLabs
   "Chi" (voice_id `5yEPTrA0uAhZsBEhHjfi`) — và key VieNeu dùng thử
   đã chạm trần 50 lượt gọi/ngày dùng chung cả team, nên để mặc
   định là job giọng lỗi. Mỗi video đều phải mở trình duyệt vào
   tab Thiết lập để đổi giọng và chờ job tạo giọng.
2. Cỡ chữ tiêu đề mặc định là "Vừa" (medium); chuẩn đã chốt cho
   các video mẫu là "Nhỏ" (small) để hộp tiêu đề không che ảnh.
   Cũng phải sửa tay trên web từng video.

Cả hai việc đều là thao tác máy móc lặp lại trên mọi video, đúng
loại việc MCP nên làm thay.

## Yêu cầu — thêm 1 tool MCP: `set_video_options`

- Tên đề xuất `set_video_options` (theo phong cách đặt tên hiện
  có: `set_audio`, `set_scene_effects`, `set_video_products`).
  Scope yêu cầu: `reels:write`, giống các tool ghi khác.
- Tham số: `video_id` (bắt buộc) + các trường tùy chọn của bộ
  `options`. **Chỉ cập nhật trường được truyền** (partial update);
  trường không truyền giữ nguyên giá trị hiện tại của video.
- Phạm vi trường: tối thiểu phải có `voice_id` và
  `title_text_size` (hai trường đang kẹt), nên làm luôn toàn bộ
  các trường mà tab "Thiết lập" của video đang cho sửa — đối
  chiếu danh sách thật trong `video_options.py` (gồm, theo dữ
  liệu `get_video` hiện trả: `voice_id`, `voice_speed`,
  `voice_volume`, `voice_pause`, `transition`, `motion`, `zoom`,
  `text_style`, `text_color`, `title_style`, `box_color`,
  `accent_color`, `box_opacity`, `title_text_style`,
  `title_text_color`, `title_box_color`, `title_accent_color`,
  `title_box_opacity`, `captions`, `text_size`,
  `title_text_size`, `text_position`, `ducking`).
- Validate dùng CHUNG một nguồn sự thật với đường web: giá trị
  hợp lệ lấy từ cùng nơi `list_edit_options` và form Thiết lập
  đang dùng, không định nghĩa lại danh sách riêng cho MCP (tránh
  lệch nhau sau này). Giá trị không hợp lệ → trả lỗi rõ ràng,
  không ghi một phần.
- `voice_id`: chấp nhận cả hai định dạng đang dùng — ElevenLabs
  (voice id trần, ví dụ `5yEPTrA0uAhZsBEhHjfi`) và VieNeu
  (`vieneu:<id>`). Nếu có sẵn danh sách giọng hợp lệ để đối
  chiếu thì kiểm tra; nếu chưa có nguồn đó, ít nhất kiểm tra
  định dạng và để job tạo giọng báo lỗi như hành vi hiện nay —
  ghi rõ lựa chọn này trong báo cáo.
- Đổi `voice_id` xong, việc tạo giọng vẫn theo cơ chế hiện tại
  (job tạo giọng chạy khi render hoặc khi bấm tạo giọng trên
  web) — tool này chỉ ghi tùy chọn, không tự gọi TTS.
- Trả về: bộ `options` đầy đủ của video sau khi cập nhật, để
  client đối chiếu ngay (khớp với những gì `get_video` trả về).
- Không đổi mặc định của team, không đụng video khác, không
  thay đổi hành vi render.

## Ngoài phạm vi

- Không thêm khả năng đăng bài / xóa video / đổi tài khoản qua
  MCP (giới hạn hiện tại của kết nối giữ nguyên).
- Tùy chọn "Dạng chữ" (giữ chữ thường) và cá nhân hóa theo tài
  khoản là brief riêng đã có ở docs/specs/chu-thuong-ca-nhan-hoa/.
  Tool này chỉ cần thiết kế dạng partial-update trên `options`
  là tự truyền được thêm trường "dạng chữ" khi brief kia làm
  xong, không cần sửa lại.

## Nghiệm thu

- `list-tools` của MCP có tool mới với schema rõ ràng.
- Đặt `voice_id` = ElevenLabs Chi + `title_text_size` = small
  cho 1 video test → `get_video` trả `options` khớp đúng 2 giá
  trị đó, các trường khác không đổi.
- Cập nhật chỉ 1 trường → các trường còn lại giữ nguyên.
- Truyền giá trị sai (ví dụ cỡ chữ không tồn tại) → bị từ chối
  kèm thông báo lỗi rõ, `options` của video không thay đổi.
- Test tự động (api) phủ: cập nhật từng phần, cập nhật giọng
  cả 2 định dạng, từ chối giá trị sai, thiếu quyền write bị
  chặn. Chạy đủ test api + web, báo cáo 3 phần theo AGENTS.md.
