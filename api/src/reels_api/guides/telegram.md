<!-- screen: telegram -->
# Hướng dẫn: Thông báo Telegram

Bot Telegram của nhóm **nhắn riêng cho bạn** về việc của chính bạn, trong đoạn chat riêng giữa bạn và bot. Nhóm chat chung chỉ nhận tin chung của cả đội ("Có gì mới" sau mỗi lần cập nhật); không ai khác thấy tin riêng của bạn.

## Kết nối (một lần)
1. Vào **Cài đặt › Thông báo Telegram**, bấm **Kết nối Telegram**.
2. Telegram mở cuộc trò chuyện với bot. Bấm **Start** (hoặc **Bắt đầu**).
3. Bot trả lời "Đã kết nối với tài khoản ...". Quay lại trang này, trạng thái chuyển thành **Đã kết nối**.

Link kết nối chỉ dùng được 30 phút. Hết hạn thì bấm **Kết nối Telegram** lại. Một tài khoản Telegram chỉ gắn với một thành viên.

## Bot nhắn gì cho bạn
- **Video của bạn chờ duyệt:** bot gửi MP4 kèm nút **Duyệt** và **Bỏ video**. Nếu video còn mục kiểm tra chưa đạt, bot liệt kê ra và hỏi lại bằng nút **Vẫn duyệt**. Duyệt trên Telegram giống bấm Duyệt trên web; hẹn giờ đăng vẫn làm trong app.
- **Việc của bạn bị lỗi:** render, đăng Facebook, TikTok, YouTube, Instagram, viết kịch bản... kèm lý do và link mở đúng chỗ trong app.
- **Kết nối hết hạn:** Fanpage, TikTok hoặc YouTube của bạn mất kết nối. Bot nhắn một lần mỗi khi kết nối hỏng; kết nối lại xong mà hỏng lần nữa thì bot nhắn lại.
- **Nhắc việc lúc 8 giờ sáng:** video của bạn đang chờ duyệt, Page của bạn sắp hết video hẹn giờ, kế hoạch 30 ngày còn ý tưởng hôm nay chưa có video. Ngày nào không có gì thì bot không nhắn.
- **Tin Muse gửi cho bạn:** khi bạn nhờ Muse làm việc, Muse có thể báo kết quả qua đây.

Tắt loại tin nào không muốn nhận bằng công tắc trên trang này. Bấm **Gửi tin thử** để kiểm tra bot nhắn được cho bạn.

## Lệnh của bot
Gõ `/` trong chat với bot (hoặc trong nhóm chung) để mở menu lệnh. Trong nhóm, chọn lệnh từ menu để Telegram tự thêm tên bot (ví dụ `/cho_duyet@rs_tool_bot`); bot chỉ nhận lệnh gọi đúng tên nó. Không lệnh nào tốn phí AI.

- `/cho_duyet`: video của bạn đang chờ duyệt. Bấm một video để nhận MP4 kèm nút Duyệt / Bỏ.
- `/hom_nay`: bài của bạn hẹn đăng hôm nay và việc cần làm (video chờ duyệt, Page sắp hết video, kế hoạch 30 ngày).
- `/loi`: việc của bạn bị lỗi trong 24 giờ qua, kèm lý do và link mở trong app.
- `/tong_quan`: số liệu hôm nay của cả nhóm (đã đăng, đã hẹn, đang chờ duyệt), chỉ có con số.
- `/moi`: các thay đổi mới nhất của app.
- `/huongdan từ khoá`: tìm trong các hướng dẫn của app, ví dụ `/huongdan hàng chờ`. Gõ `/huongdan` không kèm từ khoá để xem tất cả.
- `/help`: danh sách lệnh.

**Việc riêng luôn gửi riêng:** gõ `/cho_duyet`, `/hom_nay` hay `/loi` ngay trong nhóm thì bot chỉ trả lời "📩 Đã gửi riêng cho …" trong nhóm, còn nội dung gửi vào chat riêng của bạn. Người chưa kết nối Telegram sẽ được nhắc cách kết nối.

## Sau khi bấm Duyệt hoặc Bỏ
- **Duyệt:** nếu bạn có Page đăng nhóm chủ đề của video, bot hiện nút **➕ Hàng chờ <Page>**. Tin nhắn nói trước khung trống tiếp theo của từng Page; bấm là video vào hàng chờ của Page đó và hàng chờ xếp vào khung trống lúc đó (có thể đổi nếu có bài khác vào trước). Video có giờ trong kế hoạch còn có nút **📅 Đăng lúc <giờ>** để hẹn đúng giờ kế hoạch. Muốn giờ khác thì chọn trong app (Đăng bài, Hẹn giờ).
- **Bỏ video:** bot hỏi "Vì sao bỏ?". Trả lời ngay tin đó để ghi lý do vào video (không bắt buộc).

## Gửi link Shopee cho bot để thêm sản phẩm
Trong **chat riêng** với bot (không phải trong nhóm), dán link Shopee, mỗi dòng một link, tối đa 50 link một tin. Bot thêm chúng vào danh sách sản phẩm của bạn như nút "Thêm sản phẩm" trên web.
- Nếu bạn có **nhiều nhóm chủ đề**, ghi tên nhóm ở dòng đầu (không cần gõ dấu), rồi dán link bên dưới. Bot sẽ liệt kê các nhóm nếu bạn quên.
- Link đã có trong nhóm thì bỏ qua. Chỉ nhận link Shopee (shopee.vn, s.shopee.vn, shp.ee, shope.ee).
- Sản phẩm thêm xong là **bản nháp**. Mở **Affiliate › Sản phẩm** để bổ sung thông tin, duyệt, rồi chuyển link affiliate (xem hướng dẫn Custom Link).

## Nhóm chung
Mỗi tối lúc 21 giờ, nhóm chung nhận **Tổng kết ngày**: số video đã đăng, đã hẹn, đang chờ duyệt, và video nhiều view nhất 48 giờ qua. Không nêu việc riêng của ai.

## Ngừng nhận tin
Bấm **Ngắt kết nối** trên trang này, hoặc gửi `/stop` cho bot. Chặn bot trên Telegram cũng làm app tự ngắt kết nối.
