# Brief: Thêm nguồn ảnh Pexels + Openverse vào picker chọn ảnh

> Brief bàn giao cho coding agent. Trước khi làm, đọc `AGENTS.md`, `docs/decisions.md`,
> `docs/architecture.md` (mục Web App — Scenes), `docs/patterns.md` (mục Stock Photos)
> và brief giai đoạn 1 tại `docs/specs/ai-scene-images/brief.md`.
> Điều kiện tiên quyết: giai đoạn 1 (picker Pixabay trên web UI) đã merge.
> Lưu ý (phát hiện 2026-10-31 khi rà giai đoạn 1): kịch bản hiện KHÔNG sinh
> `keywords` cho cảnh (`OUTPUT_FORMAT` trong `claude.py` không còn trường này;
> parser vẫn nhận nếu có). Từ khóa trong picker do thành viên nhập ở ô "Từ khóa
> tìm ảnh" của cảnh hoặc ngay trong panel. Nếu mục backlog khôi phục keywords
> cho kịch bản được làm trước, ô từ khóa của panel sẽ tự điền sẵn — hành vi của
> brief này không đổi.
> Người duyệt cuối: owner. Báo cáo trong PR theo mẫu 3 phần của `AGENTS.md`.
> Ngày lập brief: 2026-10-31.

## Vấn đề

Picker sau giai đoạn 1 chỉ có một nguồn Pixabay. Kho Pixabay mỏng với món ăn và thực
phẩm đặc trưng Việt Nam (cá kho tộ, rau dền, canh chua...): tìm bằng tiếng Việt được
nhưng ít kết quả dùng được. Cần thêm 2 nguồn vào cùng lưới chọn:

- **Pexels**: ảnh thực phẩm được tuyển chọn, chất lượng cao hơn mặt bằng Pixabay, có
  lọc ảnh dọc cho khung 9:16.
- **Openverse**: gom ảnh Creative Commons từ Flickr/Wikimedia — nơi người Việt tự
  đăng ảnh món Việt kèm tiêu đề tiếng Việt, là nguồn có cơ hội ra đúng món Việt nhất.

## Sự thật đã kiểm chứng về 2 API (2026-10-31)

### Pexels

- Tìm ảnh: `GET https://api.pexels.com/v1/search`, header `Authorization: <API key>`.
  Tham số dùng: `query`, `locale=vi-VN` (Pexels hỗ trợ chính thức locale tiếng Việt),
  `orientation=portrait`, `per_page`.
- Kết quả: `photos[]` có `src` nhiều cỡ — dùng cỡ vừa (`large`/`portrait`) làm
  thumbnail cho lưới, cỡ `original`/`large2x` để tải bản lưu. `url` là trang ảnh.
- Miễn phí có key; hạn mức mặc định 200 request/giờ, 20.000 request/tháng.
- **Rủi ro ngoài tầm kiểm soát của code:** có thông tin (tháng 10/2026) Pexels tạm
  dừng cấp key mới. Vì vậy tính năng PHẢI chạy theo kiểu có-key-thì-bật: chưa có
  `PEXELS_API_KEY` thì nguồn Pexels không xuất hiện trong picker, hai nguồn còn lại
  vẫn chạy bình thường. Không được để việc thiếu key làm hỏng phần Openverse.

### Openverse

- Tìm ảnh: `GET https://api.openverse.org/v1/images/` với `q`, `license`,
  `license_type`, `page_size`. Không cần key ở mức ẩn danh (20 request/phút,
  200 request/ngày).
- Kết quả: `results[]` có `url` (ảnh gốc), `thumbnail`, `license`,
  `foreign_landing_url`, `width`/`height`.
- **Chốt cứng về giấy phép:** chỉ lấy license `cc0` và `pdm` (public domain) — gửi
  cả trong query (`license=cc0,pdm&license_type=commercial`) VÀ lọc lại phía server
  theo trường `license` của từng kết quả trước khi trả cho UI. Lý do: kênh có kiếm
  tiền (monetization + affiliate); `cc0`/`pdm` không kèm nghĩa vụ ghi credit, khớp
  với cách app hiện không hiển thị attribution. KHÔNG nới sang `by`/`by-sa`/`by-nc`
  trong việc này — muốn nới phải có quyết định riêng của owner kèm cơ chế ghi credit.

## Thiết kế

### 1. Hai client module mới, cùng khuôn với `pixabay.py`

- `api/src/reels_api/pexels.py` và `api/src/reels_api/openverse.py`, cùng hình dạng
  như client Pixabay hiện tại: `search_hits(keyword, deadline)` trả danh sách hit
  thống nhất `{url, preview}` (url = ảnh gốc sẽ tải, preview = thumbnail cho lưới);
  `download(url, deadline)` trả ảnh đã qua cùng bộ kiểm tra như Pixabay (định dạng
  JPG/PNG/WebP, ≤ 15 MB, ≤ 24 MP, không phải định dạng lạ/animated). Lỗi dịch thành
  thông điệp tiếng Việt, theo khuôn lỗi của Pixabay.
- Cấu hình qua `.env` theo mẫu base-URL sẵn có: `PEXELS_API_KEY`, `PEXELS_API_URL`
  (mặc định `https://api.pexels.com`), `OPENVERSE_API_URL` (mặc định
  `https://api.openverse.org`). Biến mới PHẢI vào bảng trong `docs/deployment.md`
  và `.env.example` trong cùng PR (luật repo).

### 2. Endpoint picker nhận thêm nguồn

Giữ nguyên hành vi của 3 endpoint Pixabay ở giai đoạn 1 (không phá UI đang chạy),
thêm cặp endpoint theo nguồn trong `routes_videos.py`:

- `GET /scenes/{scene_id}/stock?q=<từ khóa>&source=pixabay|pexels|openverse` →
  `{keyword, source, hits: [{url, preview}]}`. Với `source=pixabay` kết quả phải
  giống hệt endpoint Pixabay cũ.
- `POST /scenes/{scene_id}/stock` — body `{source, keyword, url}`. Server kiểm tra
  lại `url` có thuộc kết quả tìm của đúng nguồn + đúng từ khóa đó không (giữ nguyên
  kỷ luật chống URL bịa như endpoint chọn Pixabay hiện tại), tải bản gốc, lưu qua
  `_store_photo` với `image_source` = URL ảnh của nguồn đó (nhất quán với Pixabay).
- `GET /stock/sources` → danh sách nguồn kèm trạng thái khả dụng, ví dụ
  `[{"id": "pixabay", "available": true}, {"id": "pexels", "available": false},
  {"id": "openverse", "available": true}]`. Pexels `available=false` khi chưa cấu
  hình key. UI dựng nút chuyển nguồn từ dữ liệu này, không tự đoán phía client.

### 3. Web UI: chuyển nguồn trong cùng panel chọn ảnh

- Panel chọn ảnh của giai đoạn 1 thêm hàng chuyển nguồn (segmented control):
  Pixabay / Pexels / Openverse. Nguồn nào `available=false` thì không hiện (hoặc
  hiện mờ kèm chú thích "chưa cấu hình" — chọn một cách và ghi rõ trong PR).
- Đổi nguồn thì tìm lại bằng chính từ khóa đang có trong ô; lưới, thao tác chọn,
  trạng thái loading/lỗi giữ nguyên như giai đoạn 1. Lỗi của từng nguồn hiện nguyên
  thông điệp tiếng Việt từ api; một nguồn lỗi không làm hỏng các nguồn khác.
- Nút nhanh "Tìm ảnh" (find-image) GIỮ NGUYÊN là Pixabay — không mở rộng trong
  việc này.

### 4. Fake cho test

- Mở rộng `api/scripts/fake_services.py`: fake Pexels và fake Openverse với kết quả
  đóng hộp, gồm ít nhất: 1 kết quả Openverse mang license KHÔNG phải cc0/pdm (để
  chứng minh bộ lọc giấy phép hoạt động), 1 kết quả có URL gốc chết (để chứng minh
  đường lỗi "ảnh không tải được"). TUYỆT ĐỐI không gọi API thật trong test.

## Không làm

- Không đụng vào lõi render CLI (`worker/reels_render`): phía CLI giữ nguyên nguồn
  Pixabay duy nhất như `docs/patterns.md` đang quy định. Việc này chỉ mở rộng picker
  của WEB APP.
- Không thêm nguồn nào khác ngoài Pexels + Openverse; không dùng Unsplash.
- Không nới danh sách license của Openverse; không xây cơ chế hiển thị attribution.
- Không đổi nút find-image và không tự gán ảnh từ 2 nguồn mới.

## Tiêu chí nghiệm thu

1. Picker có đủ 3 nguồn khi đã cấu hình `PEXELS_API_KEY`; bỏ key ra thì nguồn Pexels
   biến mất khỏi picker, Pixabay + Openverse vẫn chọn ảnh được.
2. Tìm "cá kho tộ" ở nguồn Openverse: mọi ảnh trong lưới đều có license `cc0` hoặc
   `pdm` (kiểm chứng bằng fake chứa kết quả `by` bị loại ra).
3. Chọn 1 ảnh từ mỗi nguồn trong 3 nguồn → cảnh có ảnh, `image_source` là URL của
   đúng nguồn đó, render không còn bị chặn vì cảnh đó.
4. Gửi `POST /scenes/{id}/stock` với URL không thuộc kết quả tìm → bị từ chối như
   endpoint Pixabay hiện tại.
5. Openverse trả URL gốc chết → lỗi "Ảnh này không tải được, hãy chọn ảnh khác"
   (422), cảnh giữ nguyên trạng thái chưa có ảnh.
6. Pexels bị 429 (hết hạn mức giờ) → thông điệp lỗi tiếng Việt hiện trong panel,
   chuyển sang Pixabay/Openverse vẫn tìm được.
7. Test xanh: `ruff`, `pytest` (api — có test cho cả 3 nguồn qua fake, gồm lọc
   license Openverse và kiểm tra URL khi chọn), `lint` + `typecheck` + `test:e2e`
   (web) với luồng chuyển nguồn. Không lượt gọi API thật nào trong test.

## Trường hợp biên phải xử lý

- Từ khóa tiếng Việt có dấu phải được mã hoá đúng khi gọi cả 2 API (kiểm chứng bằng
  test với từ khóa "xương khớp", "cá kho tộ").
- Kết quả Openverse thiếu `thumbnail` hoặc thiếu kích thước → loại khỏi lưới, không
  hiện ô trống vỡ giao diện.
- Openverse chạm trần ẩn danh 200 request/ngày → lỗi hiện rõ, không crash picker.
- Ảnh Pexels cỡ `original` quá nặng → `download` vẫn áp trần 15 MB như Pixabay; nếu
  bản gốc vượt trần thì thử cỡ `large2x` trước khi bỏ cuộc (ghi rõ hành vi này
  trong code/PR).

## Việc ghi chép đi kèm (cùng PR)

- `docs/architecture.md`: picker web app có 3 nguồn stock; CLI vẫn Pixabay.
- `docs/decisions.md`: thêm quyết định có ngày — nguồn stock của picker web app mở
  rộng thêm Pexels + Openverse; Openverse chỉ nhận `cc0`/`pdm` để tránh nghĩa vụ
  attribution; Pexels bật theo key. (Quyết định cũ "stock chỉ ở CLI / nguồn cố định
  Pixabay" được ghi rõ là còn áp dụng cho CLI.)
- `docs/deployment.md` + `.env.example`: các biến môi trường mới.
- Gỡ mục backlog tương ứng khi xong.
