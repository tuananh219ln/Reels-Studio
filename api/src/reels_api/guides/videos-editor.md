<!-- screen: videos -->
# Hướng dẫn: chỉnh sửa, render và đăng video

Trang một video (`/videos/<số>`) tự cập nhật khi có job chạy và khi đồng đội sửa cùng lúc.

## Đầu trang cố định
- Hàng trên: **← Danh sách video**, tiêu đề, trạng thái, ai đang chỉnh sửa; các nút **Chỉnh sửa / Xong**, **⋯**, **Xem trước**, **Render** (nút chính).
- Hàng dưới là **thanh tiến độ**: Kịch bản → Ảnh (số cảnh đã có ảnh hoặc clip) → Render → Đăng → Affiliate → 48 giờ. Dấu xanh là xong, dấu cam là cần xem, đồng hồ xám là chưa tới. Bấm một bước để nhảy tới tab liên quan.
- **QC:** sau khi có MP4, chip QC cho biết video đạt hay còn mục chưa đạt; bấm để xem chi tiết.
- Nút ⌃ thu đầu trang gọn lại; một nhãn nhỏ vẫn cho biết việc cần xem.

## Video này được làm như thế nào
Thẻ gấp dưới dòng "Chủ đề…, tạo bởi…". Mở ra có hai tab:
- **Cách làm:** ai tạo, lúc nào, bằng cách nào (Muse qua MCP, AI của nhóm, tự viết, nhân bản…), nhóm, **giọng từng cảnh** kèm nguồn (VieNeu, ElevenLabs, Gemini, Google, MP3 tải lên; trộn nhiều nguồn thì có nhãn cam), nhạc, thời gian từ lúc tạo tới lúc render xong, và **dòng thời gian** các job, các bước duyệt và các lần sửa. **Sao chép hồ sơ video** copy cả thẻ thành chữ để dán vào báo cáo hoặc chat.
- **Lịch sử sửa:** mỗi lần sửa video hoặc cảnh (trên web hay qua Claude/Muse): ai sửa, lúc nào, mục nào, cũ → mới. **Hoàn tác** đưa lần sửa đó về giá trị cũ thành một lần sửa mới, không xoá gì. Nếu sau đó đã có người sửa cùng mục, app báo và không đè lên. Giọng đã tạo và MP4 không hoàn tác được: hoàn tác xong thì render lại như mọi lần sửa. Lịch sử bắt đầu từ 26/11/2026; thay ảnh/clip và thêm, xoá, đổi thứ tự cảnh chưa được ghi.

## Tiêu đề
Ô **Tiêu đề** trên danh sách cảnh mở một bảng nhỏ:
- **Chọn 1 tiêu đề gợi ý** của kịch bản, hoặc **tự nhập** rồi bấm **Lưu**: cả hai ghi vào chữ cảnh tiêu đề (5 gợi ý không đổi).
- **Không dùng tiêu đề:** xoá chữ cảnh tiêu đề (chữ cũ được cất lại) và cho duyệt video dù nhóm bắt tiêu đề. Bỏ tick thì chữ cũ quay lại; gõ một tiêu đề mới thì ô này tự bỏ tick.
- Dòng **Trên màn hình sẽ hiện: …** cho biết chữ sẽ hiện. Đổi tiêu đề sau khi render thì cần render lại trước khi duyệt.

## Các cảnh (cột trái)
- Mỗi cảnh có ảnh hoặc clip, chữ trên màn hình, lời đọc và chuyển động. **Cảnh chưa có ảnh sẽ chặn việc render.**
- Cách có ảnh cho cảnh: tải lên, dán link, lấy từ Kho tư liệu, tìm ảnh kho miễn phí (Pexels, Unsplash, Pixabay…) hoặc ảnh AI.
- Bấm **Chỉnh sửa** để sửa chữ, thứ tự, hiệu ứng và chuyển động của từng cảnh.

## Bảng bên phải: ba tab
1. **Đăng bài:** thẻ trạng thái, xem và tải MP4, **Render lại**, chọn nền tảng (Facebook, Instagram, TikTok, YouTube Shorts) rồi **Đăng ngay** hoặc **Hẹn giờ**. Bên dưới là **Nội dung đăng** (caption có nút "Copy caption + hashtag") và **Hashtag**. Chỉ đăng lên Page của chính bạn.
2. **Bình luận & Sản phẩm:** **Bình luận** ghim (có "Copy ghim", dòng khảo sát), **Bình luận thêm** (tối đa 5), **Bình luận aff tự động** và **Sản phẩm Shopee** (gợi ý của AI, tìm từ Shopee, sản phẩm đã duyệt, hoặc dán link). Link sản phẩm nằm sau bình luận ghim. Facebook không cho app tự ghim bình luận, nên bạn ghim tay.
3. **Thiết lập:** các cài đặt riêng của video này (như giọng đọc, nhạc, chữ và phụ đề), bắt đầu theo cài đặt của nhóm. Đầu tab có công tắc **Giữ media** (xem "Dọn media" bên dưới).

## Render và đăng
1. Đủ ảnh cho mọi cảnh → **Render** (có thể **Xem trước** trước). App dựng MP4 9:16.
2. Xem lại MP4 → chọn nền tảng → **Đăng**. Nếu QC đỏ, app hỏi lại trước khi cho đăng.
3. Video Facebook xong thì Page tự viết bình luận ghim và link sản phẩm; bạn ghim tay.
4. Sau 48 giờ, app đọc view, share và so với trung vị của Page.

## Dọn media sau khi đăng
Ổ lưu file của app có hạn, nên khi bật tính năng này, vài ngày (mặc định 30) sau lần đăng cuối, app tự **xoá ảnh, clip, lời đọc và nhạc riêng** của video đã đăng. **MP4, ảnh thu nhỏ và mọi số liệu vẫn giữ**, nên danh sách, thống kê và việc đăng thêm nền tảng không đổi.
- **Không dọn** video chưa đăng, video còn bài hẹn giờ hoặc trong hàng chờ, video đang có người sửa, video thắng (từ 3 lần trung vị của Page) và video vừa được nhân bản hoặc xáo cảnh.
- **Báo trước 3 ngày:** video sắp dọn có dòng "Media sẽ được dọn từ ngày …" ở tab Thiết lập, và bạn nhận nhắc việc 8:00 qua Telegram riêng.
- **Muốn giữ:** mở tab **Thiết lập**, bật **Giữ media**. Làm trước ngày dọn, vì file đã xoá không lấy lại được.
- **Video đã dọn** hiện "Đã dọn media" và không render, nhân bản y hệt, xáo cảnh hay làm bản TikTok được nữa (nhân bản bằng AI vẫn dùng được).

## Khi gặp trục trặc
- **Job lỗi:** nút **Thử lại** ở thẻ lỗi hoặc ở Nhật ký job.
- **"MP4 cũ hơn bản sửa":** bạn sửa cảnh sau lần render cuối, bấm **Render lại**.
- **Đăng thất bại:** hàng nền tảng hiện lý do màu đỏ và nút **Thử lại**.

## YouTube: riêng tư và claim bản quyền
- App tải video lên YouTube ở chế độ **riêng tư**. Hàng YouTube màu cam ghi **"Riêng tư, chưa công khai"** và chưa tính vào "Đã đăng lên X/Y nền tảng". Bấm **YouTube Studio ↗** để mở video và bật công khai.
- **Trước khi công khai**, xem mục Hạn chế / Bản quyền của video trong YouTube Studio. Nhạc nền có thể bị claim Content ID dù có giấy phép miễn phí.
- Gặp claim: ở thẻ Đăng bài bấm **Ghi claim YouTube**, ghi nhạc nào bị claim, ai claim, ngày. Hàng YouTube chuyển đỏ **"Bị chặn (claim)"** và bạn đăng lại YouTube được (ví dụ bản render với nhạc khác). Xử lý xong trong Studio (xoá bài hát, kháng nghị thắng, thay video) thì bấm **Đã xử lý claim**.
- Claim do nhạc nền: vào **Thư viện nhạc**, **Sửa** bài đó, bật **Đã bị claim trên YouTube**. Từ đó không video nào chọn được bài này, kể cả làm nhạc mặc định. Video đã có bài này giữ nguyên: đổi nhạc rồi render lại nếu cần.

## Chữ PC Shopee: Cộng dồn, số thứ tự và tiêu đề 3 dòng
- Video nhóm **PC Shopee** bật phụ đề **Cộng dồn**: lời đọc hiện dần từng từ ở nửa dưới màn hình, cụm đầu nảy vào và cụm cuối mờ đi. Chữ cảnh bị thay bằng phụ đề này.
- Cảnh có số thứ tự ở đầu chữ (ví dụ `3. *LOGITECH G304*`) giữ **vòng tròn cam** có số đó trong 2,5 giây đầu cảnh, ngay trên phụ đề.
- Khi viết kịch bản, AI tự tách **tiêu đề thành 3 dòng** (dòng nhỏ, dòng chính, dòng phụ, nhãn). Phần câu thừa (ví dụ "xem trước khi mua") được chuyển xuống **đầu caption**. Bạn vẫn sửa 4 ô chữ tiêu đề như trước.
- Xem trước trên web chỉ hiện hình đã dừng, chưa có chuyển động: hãy xem MP4 đã render để thấy hiệu ứng.
