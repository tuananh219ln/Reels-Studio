# Brief: Công tắc kiểu video theo nhóm chủ đề (Slide ảnh / Video xuyên suốt / Xen kẽ theo ngày)

Nhánh: `feat/video-mode-group-switch`

**Brief này thay thế toàn bộ brief "thêm video_mode cho create_video_from_script" trước đó trong cùng thư mục này** — việc đó nay là một phần nhỏ của Phần 3.

## Bối cảnh và quyết định của owner (2026-11-10)

Mỗi video có kiểu dựng `Video.mode`: `"slides"` (Slide ảnh từng cảnh; mặc định) hoặc `"single"` — "Video xuyên suốt": một ảnh nền chạy suốt video, ảnh từng cảnh hiện dạng lớp chồng lên nền.

Owner quyết định xen kẽ 2 kiểu cho 2 page của mình trong giai đoạn 1, theo quy tắc: **ngày dương lịch lẻ → Video xuyên suốt, ngày dương lịch chẵn → Slide ảnh**. Quy tắc này không được nằm rải rác trong lệnh của từng công cụ tạo video — owner yêu cầu **một công tắc trên chính nhóm chủ đề**, để mọi đường tạo video trong nhóm (tạo tay trên web, dịch vụ AI của team, bán tự động chuẩn bị 08:00, trợ lý qua MCP) đều cho ra cùng một kiểu.

Tiền lệ sẵn có: `KnowledgeTopic` đã mang sẵn các mặc định theo nhóm (`voice_id`, `photo_hint`, …) và màn cài đặt nhóm đã có chỗ cho chúng — công tắc này đi đúng khuôn đó.

## Hiện trạng đã kiểm chứng (code + production, 2026-11-10)

- Đường prompt nhóm qua MCP đã hỗ trợ `video_mode` đầy đủ: `get_script_prompt` nhận `video_mode` và trả prompt theo kiểu; `create_video_from_group_prompt` truyền vào `NewVideoBody(video_mode=...)` → `videos.start_video`.
- Đường kịch bản chữ thuần `create_video_from_script` chưa truyền `video_mode` → luôn `slides`.
- `create_video` (đường AI của team) không có tham số kiểu.
- `get_video` đã trả trường `mode` của video.

## Phần 1 — Cài đặt trên nhóm chủ đề

- `KnowledgeTopic` thêm một trường cài đặt kiểu video, 3 giá trị: `"slides"` | `"single"` | `"alternate"` (tên trường do người làm đặt theo quy ước sẵn có của model). Migration với **mặc định `"slides"`** cho mọi nhóm hiện hữu — không nhóm nào đổi hành vi cho tới khi chủ nhóm tự bật.
- Nghĩa của `"alternate"`: tại thời điểm tạo video, lấy **ngày dương lịch theo Asia/Saigon** — ngày lẻ → `"single"`, ngày chẵn → `"slides"`.

## Phần 2 — Một điểm phân giải duy nhất

Trong `videos.start_video` (hoặc đúng chỗ xử lý `NewVideoBody` — người làm chọn điểm mà MỌI đường tạo đều đi qua):

- Kiểu chỉ định riêng cho lần tạo này (`video_mode` được truyền vào) **thắng** cài đặt nhóm.
- Không chỉ định → theo cài đặt nhóm (`"alternate"` thì tính chẵn/lẻ như Phần 1).
- Mọi đường tạo đều kế thừa, không sửa riêng từng đường: tạo tay trên web, `create_video` (AI team), bán tự động `prepare()`, và cả 2 đường MCP ở Phần 3. Đặc biệt kiểm chứng đường bán tự động: video nó tạo lúc 08:00 phải cùng kiểu với ngày hôm đó.

## Phần 3 — MCP: kiểu thành tham số tùy chọn, mặc định theo nhóm

- `create_video_from_script`: thêm `video_mode` như brief cũ — nhưng kiểu `Literal["slides", "single"] | None = None`; truyền vào `NewVideoBody(video_mode=...)` chỉ khi được chỉ định (hoặc truyền thẳng `None` nếu `NewVideoBody` đã hiểu `None` = theo nhóm — theo đúng thiết kế ở Phần 2).
- `get_script_prompt` và `create_video_from_group_prompt`: mặc định của `video_mode` đổi từ `"slides"` thành `None` (= theo nhóm). `get_script_prompt` phải trả về `video_mode` **đã phân giải** (kiểu thật sẽ dùng) để phía viết kịch bản viết đúng định dạng của kiểu đó.
- Docstring của cả 3 tool ghi rõ: "không truyền `video_mode` = theo công tắc kiểu video của nhóm".

## Phần 4 — Giao diện web

- Màn cài đặt của nhóm chủ đề (chỗ đang đặt giọng mặc định / gợi ý ảnh) thêm công tắc 3 nấc, nhãn rõ ràng: **"Slide ảnh"**, **"Video xuyên suốt"**, **"Xen kẽ theo ngày (ngày lẻ: xuyên suốt, ngày chẵn: slide)"**. Mặc định hiển thị `"slides"`.
- Hộp thoại tạo video trong nhóm hiển thị sẵn kiểu sẽ dùng (đã phân giải theo công tắc + ngày) và vẫn cho chọn riêng cho video đó như hiện tại.

## Ngoài phạm vi

- Không tự đặt nhóm nào sang `"alternate"` trong code/migration — owner tự bật cho 2 nhóm của mình trong giao diện sau khi deploy.
- Không đổi quy tắc chẵn/lẻ; không đụng renderer; không đổi `Video.mode`.

## Kiểm thử

Theo mẫu test hiện có của API và MCP:

- Ma trận phân giải tại điểm tạo video: chỉ định riêng thắng nhóm; nhóm `"single"`; nhóm `"slides"`; nhóm `"alternate"` với ngày lẻ và ngày chẵn (đóng băng ngày khi test); nhóm chưa từng đặt gì → `"slides"`.
- MCP: `create_video_from_script` với `video_mode="single"` → `mode == "single"`; không truyền + nhóm `"single"` → `"single"`; `get_script_prompt` không truyền `video_mode` trả về kiểu đã phân giải của nhóm.
- Bán tự động: `prepare()` tạo video theo kiểu đã phân giải của nhóm/ngày (test hoặc kiểm chứng bằng đọc code + test ở tầng `start_video` nếu `prepare` đi qua đó — ghi rõ trong báo cáo cách đã kiểm chứng).
- Các test hiện có vẫn xanh.

## Ghi quyết định

Ghi một file MỚI `docs/decisions/2026-11-10-video-mode-group-switch.md` (không append vào `docs/decisions.md`): kiểu video là cài đặt theo nhóm chủ đề với 3 nấc (slides / single / alternate — ngày lẻ xuyên suốt, ngày chẵn slide, giờ Asia/Saigon), độ ưu tiên: chỉ định riêng cho video > công tắc nhóm > slides; mọi đường tạo video đều qua một điểm phân giải.

## Quy tắc làm việc

- Đọc `AGENTS.md` và các file trong `docs/decisions/` trước khi làm. **TUYỆT ĐỐI không dùng subagent.** Làm theo TDD.
- Báo cáo 3 phần khi xong: Done / Verified / Remaining risks. Không tự commit/merge khi chưa được duyệt.
