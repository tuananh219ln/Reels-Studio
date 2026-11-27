<!-- screen: affiliate -->
# Hướng dẫn: gắn link affiliate hàng loạt bằng Custom Link của Shopee

Dành cho thành viên team. Shopee chưa cấp Open API cho tài khoản, nên app không tự đổi link sản phẩm thành link
affiliate được. Cách làm hiện tại: app chuẩn bị file, bạn tải lên Shopee một lần, rồi nhập file kết quả về.

## Khi nào dùng
- Sản phẩm đã duyệt nhưng **chưa có link affiliate** (cột Link ghi "Chưa có link", hoặc cột "3 · Cần link" ở dạng Quy trình).
- Bạn muốn đơn hàng được **tính về đúng Page** (mỗi dòng gắn mã Page ở cột `Sub_id1`).

## Các bước trên web
1. Vào **Affiliate › Sản phẩm**, chọn **nhóm chủ đề** (nút xuất cần biết nhóm).
2. Bấm **Nhập / Xuất › Xuất file Custom Link (Excel)** (hoặc nút ở cột "Cần link" của dạng Quy trình). Nếu nhóm có nhiều Page, chọn Page.
   Tick "Gồm cả món đã có link" nếu muốn chuyển đổi lại cả những món đã có.
3. Tải file `.xlsx` về, vào **Shopee Affiliate › Custom Link**, tải file đó lên (tối đa 10.000 link mỗi lần).
   Chờ trạng thái "Đã tạo" ở trang **Quản lý xuất dữ liệu**, tải **file CSV kết quả** về.
4. Quay lại app, bấm **Nhập / Xuất › Nhập kết quả Shopee** (hoặc nút cùng tên ở cột "Cần link"), chọn file CSV.
5. Đọc bảng xem trước: **Sẽ gắn link** (sẽ ghi), **Của đồng đội** (giữ nguyên), **Lỗi** (kèm lý do, gồm cả lý do Shopee ghi ở cột
   "Lí do thất bại"). Nếu ổn, bấm **Gắn link cho N sản phẩm**.

## Chuyển bằng tiện ích Chrome (không cần tải file)
Cần tiện ích Reels Studio từ phiên bản 1.8.0 (xem `extension/README.md`) và **đã đăng nhập affiliate.shopee.vn** trên cùng Chrome.
1. Bước 1 và 2 như trên, nhưng trong hộp "Xuất file Custom Link" bấm **Chuyển bằng tiện ích Chrome**.
2. Tiện ích tự gửi link sang Shopee Custom Link bằng tab Shopee của bạn (không dùng tài khoản của ai khác), kèm `Sub_id1` là Page.
3. Bảng xem trước hiện ra như khi nhập file. Đọc rồi bấm **Gắn link cho N sản phẩm**.
Nếu báo chưa đăng nhập hoặc Shopee không trả lời như mong đợi, dùng cách file Excel ở trên.

## Các bước với trợ lý (MCP)
Kết nối trợ lý với app (xem `docs/chatgpt.md`), rồi nói ví dụ:
- "Liệt kê link cần chuyển đổi của nhóm Già Mà Khỏe." → trợ lý cho danh sách link gốc và mã `Sub_id1` (`p<id>`).
- Bạn đưa danh sách đó cho Shopee Custom Link (điền cột Sub_id1 cho mọi dòng), tải CSV kết quả về.
- "Dán CSV này và xem trước giúp tôi." → trợ lý gọi bước xem trước và đọc lại kết quả cho bạn.
- "Ổn rồi, nhập đi." → chỉ khi đó trợ lý mới ghi.
Trợ lý **không** tự tải lên Shopee và **không** ghi gì trước khi bạn đồng ý.

## Cần biết
- **Chỉ đổi sản phẩm do chính bạn thêm** trong nhóm. Sản phẩm của đồng đội giữ nguyên link của họ.
- **Link mới thay link cũ** của sản phẩm. Bình luận đã đăng dưới bài đang live sẽ được sửa theo link mới.
- **Đơn chỉ đo được tới Page, không tới từng video**, vì mã Page đã gắn cứng lúc chuyển đổi.
- **Nhóm có nhiều Page:** mỗi sản phẩm chỉ có một link, nên đơn chỉ đo về Page bạn chọn khi xuất.
- Nếu Page có tài khoản Shopee riêng có API, bình luận tự tạo link riêng và **không dùng** link bạn nhập.

## Khi có lỗi
| Thông báo | Nguyên nhân và cách xử lý |
| --- | --- |
| Shopee: "Đăng tải thất bại, vui lòng sử dụng bản mẫu có sẵn" | Không tải file tự làm hay file từ "Xuất danh sách (CSV)". Chỉ dùng file từ "Xuất file Custom Link (Excel)". |
| "Nhóm này có N Page đăng… hãy chọn Page" | Nhóm có nhiều Page: chọn một Page trong hộp xuất. |
| "Không có sản phẩm nào cần xuất" | Cần sản phẩm đã duyệt, do bạn thêm, có link sản phẩm gốc, chưa có link (hoặc tick "Gồm cả món đã có link"). |
| Dòng **Lỗi**: "Link gốc không khớp sản phẩm nào của bạn" | Sản phẩm không thuộc bạn hoặc không ở nhóm đã chọn. |
| Dòng **Lỗi**: "Shopee không chuyển đổi được: …" | Đọc lý do Shopee ghi; thường là link gốc hỏng. |
| "Không thấy cột “Liên kết gốc”" | Bạn chọn nhầm file; dùng file CSV Shopee trả về sau khi chuyển đổi. |
