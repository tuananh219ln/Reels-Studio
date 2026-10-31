# Brief: Tự động có ảnh cho cảnh chưa có ảnh

> Brief bàn giao cho coding agent. Trước khi làm, đọc `AGENTS.md`, `docs/decisions.md`,
> `docs/architecture.md` (mục Web App — Scenes, Render Core) và `docs/patterns.md`.
> Người duyệt cuối: owner. Báo cáo trong PR theo mẫu 3 phần của `AGENTS.md`.
> Ngày lập brief: 2026-10-31.

## Vấn đề

Kịch bản sinh xong thì mỗi cảnh mới chỉ có chữ: `image_prompt` và `keywords`. Muốn render,
thành viên phải tự tìm/tải/upload ảnh cho từng cảnh (cả cảnh tiêu đề). Đây là khâu tốn
thời gian nhất trong vòng tạo nội dung và là lý do video mới tạo "chưa tự có ảnh".
Backlog đã ghi hướng này ngày 2026-10-28: "Tạo ảnh bằng AI cho cảnh thiếu ảnh — nội dung
gốc thay cho ảnh stock".

## Sự thật trong code hiện tại (đã rà soát 2026-10-31)

- Phía api ĐÃ có sẵn 3 endpoint Pixabay mà web UI chưa hề dùng:
  - `POST /scenes/{id}/find-image` — tự tìm 1 ảnh theo `scene.keywords`, tải về và lưu
    qua `_store_photo` với `image_source` = URL Pixabay (`routes_videos.py`).
  - `GET /scenes/{id}/pixabay` — trả danh sách ảnh để người dùng chọn (picker).
  - `POST /scenes/{id}/pixabay` — tải ảnh người dùng đã chọn trong picker về storage.
- Client Pixabay đã có: `api/src/reels_api/pixabay.py` (tìm tiếng Việt, xoay vòng kết
  quả qua tham số `after`, tải ảnh có kiểm tra). Key cấu hình bằng `PIXABAY_API_KEY`
  trong `.env` (xem `docs/deployment.md`).
- Kịch bản đã sinh sẵn `keywords` cho từng cảnh (xem `claude.py`, `GeneratedScene`), và
  `save_script` trong `jobs.py` đã lưu keywords xuống DB — find-image chạy được ngay
  trên video vừa sinh kịch bản.
- Quyết định đang hiệu lực (`docs/decisions.md`, 2026-10-31): render phía server chỉ
  dùng ảnh/clip thành viên đã lưu cho cảnh; ảnh stock tự tìm chỉ có ở CLI. Brief này
  KHÔNG đảo quyết định đó: render vẫn chặn cảnh thiếu ảnh như cũ; tính năng mới chỉ
  giúp cảnh có ảnh TRƯỚC khi render, và mọi ảnh tự động đều phải được lưu vào cảnh
  (qua cùng đường `_store_photo`) để thành viên nhìn thấy và thay được.

## Phạm vi

### Giai đoạn 1 — Đưa endpoint Pixabay sẵn có lên web UI (không sửa backend)

Trên thẻ của từng cảnh trong trình sửa video (kể cả cảnh tiêu đề):

- Nút "Tìm ảnh" gọi `POST /scenes/{id}/find-image`. Trong lúc chờ: trạng thái loading
  trên thẻ cảnh. Xong: preview ảnh cập nhật như ảnh upload. Lỗi (502 `pixabay_error`,
  hết hạn mức, không có kết quả): hiện nguyên thông điệp tiếng Việt từ api.
- Nút "Chọn ảnh" mở picker dùng `GET /scenes/{id}/pixabay`: lưới ảnh kết quả cho
  keywords của cảnh, bấm một ảnh thì gọi `POST /scenes/{id}/pixabay` để lưu.
- Cảnh đã có ảnh vẫn bấm "Tìm ảnh" lại được để đổi ảnh khác (endpoint đã hỗ trợ xoay
  vòng qua `after`).
- Không thêm dependency, không đổi api.

### Giai đoạn 2 — Job tạo ảnh AI cho các cảnh còn thiếu ảnh

**Điểm cần owner chốt trước khi code:** nhà cung cấp tạo ảnh. Đề xuất mặc định:
Gemini image generation qua Google AI Studio (có free tier để test, bám prompt tiếng
Việt tốt, xuất được khung dọc 9:16). Nếu owner chọn nhà cung cấp khác, chỉ thay module
client — phần còn lại của brief giữ nguyên.

- Module client mới `api/src/reels_api/imagegen.py`, viết theo khuôn `tts.py`/
  `pixabay.py`: hàm thuần nhận prompt, trả bytes ảnh; lỗi dịch thành thông điệp tiếng
  Việt rõ ràng (hết quota, bị từ chối nội dung, timeout). Cấu hình qua `.env` theo mẫu
  base-URL sẵn có: `IMAGE_GEN_API_URL`, `IMAGE_GEN_API_KEY`, `IMAGE_GEN_MODEL`. Biến
  mới PHẢI vào bảng trong `docs/deployment.md` và `.env.example` trong cùng PR (luật
  repo).
- Job kind mới `image` trong hệ job hiện tại (bảng `jobs`, worker `jobs.py`):
  - Endpoint `POST /videos/{id}/image` (theo khuôn `/script`, `/render`) tạo job.
  - Job chạy qua MỌI cảnh của video: cảnh đã có ảnh hoặc clip thì BỎ QUA; cảnh chưa có
    thì gọi provider bằng `image_prompt` của cảnh (cảnh không có `image_prompt` thì
    dùng dòng chữ đầu tiên của cảnh), lưu kết quả qua cùng đường lưu trữ như
    `_store_photo` với `image_source` = `ai:<model>` để phân biệt với `upload` và URL
    Pixabay.
  - Tôn trọng luật hàng đợi hiện tại: 1 job chạy mỗi video, 1 job mỗi worker, job bị
    huỷ giữa chừng để lại các cảnh đã xong (giống render bị huỷ).
  - Kết quả từng phần: một cảnh lỗi (provider từ chối prompt đó) KHÔNG làm hỏng cả
    job — job kết thúc `done`, phần `detail`/log ghi rõ cảnh nào chưa có ảnh và vì
    sao. Chỉ khi provider hỏng toàn cục (sai key, hết quota) job mới `failed`.
  - Đếm số lượt gọi provider vào job như cách job script đếm lượt gọi Claude.
- Web UI: nút "Tạo ảnh AI cho cảnh thiếu" ở đầu trang video (chỉ hiện khi còn cảnh
  thiếu ảnh), chạy job `image` và cập nhật theo cơ chế polling job hiện có. Từng cảnh
  không cần nút riêng: bấm lại nút của video là đủ vì job tự bỏ qua cảnh đã có ảnh.
- Ảnh AI trả về phải qua cùng kiểm tra như ảnh upload (`uploads.py`: JPG/PNG/WebP,
  ≤ 15 MB, ≤ 24 MP) trước khi lưu; sai định dạng thì tính là cảnh đó lỗi.
- Fake cho test: mở rộng `api/scripts/fake_services.py` thêm fake image provider
  (ảnh mẫu cố định + chế độ lỗi) để pytest/E2E không gọi API thật. TUYỆT ĐỐI không
  gọi provider thật trong test (luật repo: API thật tốn tiền thật).

## Không làm

- Không tự tìm/tự tạo ảnh trong lúc render; render giữ nguyên luật chặn thiếu ảnh.
- Không ghi đè ảnh/clip thành viên đã upload hay đã chọn.
- Không lưu nguồn/giấy phép cho ảnh AI ngoài chuỗi `image_source` nói trên.
- Không đổi lõi render `worker/reels_render`.

## Tiêu chí nghiệm thu

1. Video mới sinh kịch bản: bấm "Tìm ảnh" ở một cảnh → cảnh có ảnh, preview đúng, mà
   không cần sửa backend.
2. Picker mở được, chọn ảnh khác → ảnh của cảnh thay đổi.
3. Video có 3 cảnh thiếu ảnh: bấm "Tạo ảnh AI cho cảnh thiếu" → job `image` xuất hiện
   trong `/jobs`, cả 3 cảnh có ảnh với `image_source` bắt đầu bằng `ai:`, render chạy
   được ngay sau đó.
4. Chạy lại job `image` khi mọi cảnh đã có ảnh → job xong ngay, 0 lượt gọi provider.
5. Một cảnh bị provider từ chối → job vẫn `done`, cảnh đó còn thiếu ảnh, thông điệp
   lỗi của cảnh hiển thị được cho người dùng.
6. Huỷ job giữa chừng → các cảnh đã tạo giữ nguyên, job ở trạng thái đã huỷ.
7. Toàn bộ test cũ và mới xanh: `ruff`, `pytest` (api), test worker, `lint` +
   `typecheck` + `test:e2e` (web) — E2E dùng fake provider.

## Trường hợp biên phải xử lý

- Cảnh tiêu đề không có `keywords` (find-image trả lỗi "chưa có từ khóa") → UI hiện
  đúng thông điệp đó, không crash.
- Provider trả 429/hết quota giữa job → dừng job ở trạng thái `failed` với thông
  điệp tiếng Việt, giữ các cảnh đã xong.
- Video đang bị khoá bởi job khác → endpoint trả lỗi theo luật job hiện tại.
- `IMAGE_GEN_API_KEY` chưa cấu hình → nút tạo ảnh vẫn bấm được, job `failed` ngay
  với thông điệp "chưa cấu hình" rõ ràng (theo khuôn lỗi thiếu key ElevenLabs).

## Việc ghi chép đi kèm (cùng PR)

- Cập nhật `docs/architecture.md` (thêm job `image` và nguồn ảnh `ai:`), bảng biến
  môi trường trong `docs/deployment.md`, `.env.example`.
- Ghi quyết định mới vào `docs/decisions.md` (có ngày): render server vẫn chỉ dùng
  ảnh đã lưu; thêm đường tạo ảnh AI làm một nguồn ảnh được lưu tường minh; nhà cung
  cấp đã chốt.
- Xoá mục backlog "Tạo ảnh bằng AI cho cảnh thiếu ảnh" khi giai đoạn 2 xong (giai
  đoạn 1 xong thì ghi chú tiến độ vào backlog).
