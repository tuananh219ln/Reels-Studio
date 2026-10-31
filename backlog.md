# Backlog: Reels Studio

<!-- Mục đã hoàn thành thì xóa: lịch sử nằm trong Git. -->
<!-- Mỗi mục: làm gì, vì sao, và ngày thêm. -->

## Tính năng

- Hỗ trợ đăng Reels/TikTok: lên lịch, nhắc giờ đăng (11–12h, 19–21h), gói sẵn MP4 + caption + hashtag; đăng và ghim bình luận affiliate thủ công. Vì sao: giai đoạn ưu tiên ngay sau MVP. (2026-10-28)
- Lịch chủ đề: ma trận chủ đề (tuổi thọ, tim mạch, máu não, xương khớp, gan, da tóc, giấc ngủ, giảm cân) và theo mùa (cúm, nồm, Tết). Vì sao: bước 1 của quy trình sản xuất. (2026-10-28)
- Đo chỉ số sau 48 giờ (view, share, lưu) và KPI tuần (share/view ≥ 0,2%, view trung vị, số video vượt 10× trung vị). Vì sao: tìm video thắng. (2026-10-28)
- Nhân bản video thắng: video vượt 10× trung vị → Claude đề xuất 10 biến thể (đổi thực phẩm / mốc tuổi / nhóm bệnh) xếp theo khả năng viral, làm ngay 3. Đã có: nút "Nhân bản" viết 1 biến thể theo yêu cầu đổi. Vì sao: chủ đề thắng khai thác thành chuỗi. (2026-10-28)
- Tự động đăng lên Instagram và TikTok. Đã có: đăng lên Facebook Page. TikTok không nhận công cụ nội bộ cho audit nên hướng đi là gửi vào hộp nháp của app. Vì sao: bỏ bước đăng tay. (2026-10-28)
- Affiliate Shopee tự động: tìm sản phẩm bằng Open API (`productOfferV2`), tạo link bằng `generateShortLink` với `subId` là mã video, kiểm tra lại hoa hồng hằng ngày, đọc `conversionReport` để biết doanh thu theo video. Đã có: danh sách nhập tay, duyệt, gắn vào Reel đã đăng. Cần trước: App ID và Secret của Shopee Affiliate. Vì sao: bỏ bước nhập tay và biết video nào ra tiền. (2026-10-31)
- Hỗ trợ YouTube Shorts. (2026-10-28)
- Nội dung tiếng Anh: chọn ngôn ngữ VI/EN cho từng video (kịch bản, giọng TTS, quy tắc an toàn). (2026-10-28)
- Câu miễn trừ "Tham khảo, không thay thế tư vấn bác sĩ" và câu "không phải là thuốc" cho sản phẩm TPCN. Vì sao: giảm rủi ro chính sách Meta và Luật Quảng cáo. (2026-10-28)
- Template "Thực phẩm X + Y": hook 2,3s + N cặp kết hợp chia màn hình 1/3 B-roll liền mạch trên, đĩa đồ ăn dưới (3,5s/cặp, cảnh nối 0,8s), cắt thẳng theo nhịp nhạc, không chữ trên cặp, kết thúc đột ngột để xem lại; hook có bản an toàn. Cảnh dùng video đã có; còn thiếu bố cục chia màn hình và cắt theo nhịp. Chi tiết: ux-guidelines.md (Food Pairing Template, Smooth Motion Rules). Vì sao: video tham khảo rau dền có tỷ lệ chia sẻ cao. (2026-10-30)
- Tự động gắn nhạc từ thư viện theo chủ đề video: Claude chọn nhãn topic/mood trong cùng lượt gọi kịch bản, app tự khớp và gắn track từ thư viện, không ghi đè nhạc thành viên đã chọn. Vì sao: video sinh xong chưa có nhạc, thành viên phải chọn tay dù thư viện đã gắn nhãn sẵn. Brief đã viết: `docs/specs/auto-music-match/brief.md`. (2026-10-31)
- Đăng nhập bằng Google (danh sách email được phép, callback qua /api). Vì sao: tiện cho đội, không phải nhớ mật khẩu. (2026-10-29)
- Trang sửa video trên điện thoại: thanh "Render" dính ở đáy màn hình, và nút nhảy tới phần MP4/Đăng Facebook. Vì sao: trang vẫn dài khoảng 9.000 px, phải cuộn lên đầu mới bấm được Render. (2026-10-31)
- Bảng trên điện thoại (Job logs, Người dùng, Fanpage, Bài đăng, Sản phẩm affiliate) hiện dạng thẻ thay vì cuộn ngang. Vì sao: các cột bên phải bị khuất, dễ không biết là cuộn được. (2026-10-31)

## Lỗi
