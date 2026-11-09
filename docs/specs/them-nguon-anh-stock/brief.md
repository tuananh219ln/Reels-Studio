# Brief Reels Studio — Thêm nguồn ảnh stock miễn phí: Wikimedia Commons + Unsplash

> Soạn 09/11/2026 theo quyết định của user (chủ sản phẩm).
> Cách làm theo lệ của team: đọc AGENTS.md + docs/decisions.md trước;
> nhánh riêng; TDD (viết test trước); chạy đủ test api + web; báo cáo
> 3 phần theo AGENTS.md; không tự merge; chạy inline, không dùng
> subagent.

## Bối cảnh (đã kiểm chứng khi sản xuất video 60, 61 ngày 08/11)

Bộ tìm ảnh stock của tool hiện có 3 nguồn: Pexels, Pixabay,
Openverse — dùng chung cho bộ chọn ảnh trên web và tool MCP
`search_stock_photos` (tham số `source`). Thực tế sản xuất cho
thấy kho hiện tại thiếu đúng nhóm ảnh quan trọng nhất của các
page nội dung Việt:

- Món Việt có tên riêng (canh chua cá, canh nấm nước trong,
  canh khổ qua nhồi thịt...) rất hiếm: canh nấm phải tìm 4 vòng
  cả 3 kho không ra, đành dùng ảnh nồi lẩu gần đúng.
- Openverse kết quả nhiễu nhiều (súp kem Tây, mì), ít khi dùng
  được.

Hai nguồn miễn phí bổ sung đúng chỗ thiếu này:

1. **Wikimedia Commons** — nguồn duy nhất có ảnh món Việt do
   người Việt tự chụp (đúng nhóm "hàng hiếm" ở trên). API công
   khai, KHÔNG cần API key.
2. **Unsplash** — chất lượng ảnh cao, ảnh món Á + nguyên liệu
   nhiều hơn hẳn Pexels. API cần Access Key (gói miễn phí của
   Unsplash) — key do user tạo và dán vào Cài đặt, xem mục
   nghiệm thu.

**Foodiesfeed KHÔNG nằm trong brief này**: trang đó không có
API công khai, chỉ tải tay từng ảnh qua web; cào dữ liệu về là
đường mong manh và không sạch về điều khoản. Khi cần ảnh ở đó
thì tải tay rồi đưa vào Kho tư liệu như hiện nay.

## Yêu cầu

### 1. Thêm nguồn `wikimedia` vào bộ tìm ảnh stock

- API: Wikimedia Commons (MediaWiki API, `generator=search`
  theo namespace File + `prop=imageinfo` lấy URL ảnh, URL
  trang mô tả, giấy phép và tác giả). Không cần key; gửi
  User-Agent định danh ứng dụng theo đúng yêu cầu của
  Wikimedia.
- Kết quả trả về cùng "khuôn" với 3 nguồn hiện tại (ảnh xem
  trước + URL ảnh gốc + trang nguồn) để nút chọn ảnh trên web
  và tool MCP `use_stock_photo` chạy không phải sửa.
- Ưu tiên biến thể ảnh có độ phân giải đủ cho khung dọc
  1080×1920 (dùng `iiurlwidth`/thumburl như API hỗ trợ).

### 2. Thêm nguồn `unsplash` vào bộ tìm ảnh stock

- API: Unsplash Source/Search API chính thức
  (`GET /search/photos`), xác thực bằng Access Key.
- Key lấy từ **Cài đặt của team** (thêm một trường nhập key
  Unsplash, lưu như các key dịch vụ khác, không hardcode,
  không ghi ra log). Chưa có key thì nguồn `unsplash` hiện
  trạng thái "chưa cấu hình key" ở nơi chọn nguồn, và gọi tìm
  qua MCP trả lỗi rõ ràng — không im lặng trả rỗng.
- Dùng URL ảnh do API trả về trong kết quả tìm như các
  nguồn khác.
- Xử lý giới hạn gói miễn phí (50 lượt/giờ ở mức demo): chạm
  giới hạn thì báo lỗi rõ "hết lượt Unsplash", không treo job.

### 3. Điểm tích hợp — một chỗ, hai mặt dùng

- Mở rộng đúng dịch vụ tìm ảnh stock đang phục vụ 3 nguồn
  hiện tại; KHÔNG viết đường tìm riêng cho từng mặt:
  - Bộ chọn ảnh trên web (nơi đang chọn pexels/pixabay/
    openverse) có thêm 2 lựa chọn nguồn mới.
  - Tool MCP `search_stock_photos`: tham số `source` nhận
    thêm `wikimedia` và `unsplash`.
- 3 nguồn cũ giữ nguyên hành vi; từ khóa tiếng Việt phải
  truyền được tới Wikimedia (đây là lý do chính thêm nguồn
  này — tìm "canh chua" bằng tiếng Việt).

## Ngoài phạm vi

- Không thêm Foodiesfeed (lý do ở phần bối cảnh).
- Không thay đổi luật chọn ảnh của các page (vẫn phải soi
  ảnh cỡ lớn trước khi gắn) — brief này chỉ thêm nguồn.
- Không xử lý giấy phép/ghi credit — ngoài phạm vi theo
  quyết định của chủ sản phẩm.

## Nghiệm thu

- Tìm "canh chua" với source `wikimedia` (cả trên web và qua
  MCP) trả về ảnh món Việt thật, chọn một ảnh gắn vào cảnh
  được như các nguồn cũ.
- Tìm "vegetable soup" với source `unsplash` sau khi đã dán
  key trong Cài đặt: có kết quả; chưa có key thì báo rõ chưa
  cấu hình thay vì trả rỗng.
- 3 nguồn cũ (pexels, pixabay, openverse) tìm và gắn ảnh
  vẫn như trước.
- Test tự động (api) phủ: chuẩn hóa kết quả của 2 nguồn mới
  về cùng khuôn kết quả, lỗi khi Unsplash chưa có key và khi
  chạm giới hạn lượt.
  Chạy đủ test api + web, báo cáo 3 phần theo AGENTS.md.

## Việc của user sau khi merge

- Tạo ứng dụng miễn phí trên Unsplash Developers, lấy Access
  Key và dán vào trường key trong Cài đặt của tool (key không
  gửi qua chat). Wikimedia không cần làm gì.

## Chốt sau review (09/11/2026, chủ sản phẩm)

Review đối chiếu với code và [decisions](../../decisions.md) nêu các điểm dưới đây; chủ
sản phẩm đã trả lời từng điểm.

1. **Giấy phép Wikimedia.** Ảnh món Việt trên Commons có cả Public domain lẫn
   CC BY / CC BY-SA (phải ghi tác giả). Chốt: **lấy cả ảnh CC BY/BY-SA**, đảo quyết định
   "Openverse is public-domain only" (2026-10-31) riêng cho Wikimedia, và **cảnh báo**:
   app lưu giấy phép + tác giả với cảnh, hiện nhãn cảnh báo trên web và trong danh
   sách cảnh báo trước render; tool MCP trả cảnh báo kèm dòng credit gợi ý. Muse đọc
   qua MCP rồi báo qua chat chính + WhatsApp (app không tự gửi WhatsApp). Mục "Không xử
   lý giấy phép/ghi credit" ở trên được thay bằng điểm này. Openverse giữ nguyên CC0/PD.
2. **Unsplash theo điều khoản API.** Gọi `links.download_location` khi gắn một ảnh; key
   gửi bằng header `Authorization: Client-ID …`. Hết lượt Unsplash trả `403` "Rate Limit
   Exceeded" (không phải 429) và phải báo "hết lượt Unsplash", tách khỏi lỗi sai key.
   "Unsplash Source" đã ngừng; chỉ dùng Search API.
3. **Tự tìm ảnh có hai nguồn mới.** Thứ tự chung: Pexels → Unsplash → Pixabay →
   Wikimedia → Openverse.
4. **Mỗi nhóm chủ đề tự sắp thứ tự nguồn ảnh** (cùng PR này): Kho kiến thức › nhóm có
   "Thứ tự nguồn ảnh"; để trống thì dùng thứ tự chung. Tự tìm ảnh, bộ chọn ảnh (nguồn
   mở sẵn) và nút "Tìm ảnh" của video trong nhóm đi theo thứ tự đó; MCP đọc được.
5. **Nguồn chưa có key** hiện mờ trong bộ chọn ảnh với "chưa cấu hình key" thay vì ẩn
   (cho cả Pexels/Pixabay), gọi qua MCP thì báo lỗi rõ.
6. Từ khóa tiếng Việt đi trước cho Wikimedia (như Openverse); Wikimedia chỉ lấy ảnh
   bitmap (JPG/PNG/WebP), User-Agent có thông tin liên hệ theo chính sách Wikimedia.
