# Brief Reels Studio — Tùy chọn chữ thường khi render + cá nhân hóa theo tài khoản

> Soạn 08/11/2026 theo quyết định của user (chủ sản phẩm).
> Cách làm theo lệ của team: đọc AGENTS.md + docs/decisions.md trước;
> nhánh riêng; TDD (viết test trước); chạy đủ test api + web; báo cáo
> 3 phần theo AGENTS.md; không tự merge.

## Bối cảnh (đã kiểm chứng 08/11)

1. **Chữ trên video bị ép viết hoa.** Dữ liệu chữ lưu dạng câu thường,
   nhưng bản render và cả bản xem trước trong editor đều hiện viết hoa
   toàn bộ. Đã kiểm tra kỹ cả 3 nơi: Thiết lập của từng video, Cài đặt
   › Mặc định video của cả team, và hộp thoại định nghĩa "kiểu hộp
   chữ" — không có bất kỳ tùy chọn nào về dạng chữ (hoa/thường) hay
   font; định nghĩa một kiểu chữ hiện chỉ gồm: tên kiểu, màu nền hộp,
   độ trong, màu chữ, màu chữ đánh dấu. Viết hoa đang là hành vi ép
   cứng ở khâu vẽ chữ khi render.
2. **Tool dùng chung nhưng cài đặt lại dùng chung nốt.** Nhiều thành
   viên dùng chung một tool, mỗi người có Page, topic và thói quen
   thiết lập riêng; nhưng "Mặc định video" hiện là một bộ duy nhất cho
   cả team (một người sửa là mọi người bị ảnh hưởng), danh sách Page
   không lọc theo người, và Fanpage chưa có thông tin chủ sở hữu
   (đã ghi nhận từ 02/11 — trong khi mô hình tiền của team đã chốt là
   tiền-riêng-theo-người, đơn vị sở hữu là từng lượt đăng theo tài
   khoản).

## Phần A — Tùy chọn giữ chữ thường (phần nhỏ, làm trước, độc lập)

- Thêm tùy chọn **"Dạng chữ"** cho cả chữ các cảnh và chữ cảnh tiêu
  đề, 2 giá trị:
  - "Giữ nguyên như đã nhập" — render đúng hoa/thường như dữ liệu
    (viết thường như câu bình thường).
  - "Viết hoa toàn bộ" — hành vi hiện tại.
- Tùy chọn này xuất hiện ở: Thiết lập của từng video, và ở Mặc định
  video (làm giá trị khởi tạo cho video mới).
- Render phải tôn trọng lựa chọn ở mọi chỗ vẽ chữ: chữ trên cảnh,
  hộp tiêu đề, và các từ đánh dấu trong *dấu sao* (phần tô màu giữ
  nguyên, chỉ thay đổi hoa/thường). Bản xem trước trong editor phải
  khớp bản render.
- Video cũ và video không đặt tùy chọn này: giữ hành vi hiện tại
  (viết hoa) để không làm thay đổi video của người khác.
- **Nghiệm thu:** một video đặt "Giữ nguyên như đã nhập" render ra
  chữ thường đúng từng chữ như dữ liệu đã lưu; cùng video đó đặt
  "Viết hoa toàn bộ" render giống hệt hành vi hiện nay; test tự động
  phủ cả 2 trường hợp cho cảnh thường và cảnh tiêu đề.

## Phần B — Cá nhân hóa theo tài khoản đăng nhập (chia giai đoạn, làm sau khi duyệt phạm vi)

**Nguyên tắc do user chốt (08/11):** các phần cài đặt và những phần
liên quan đến cá nhân phải đi theo tài khoản đã đăng nhập; các danh
sách nên có bộ lọc và giá trị mặc định theo user.

- **B1. Mặc định theo user.** Mỗi tài khoản thành viên có bộ "Mặc
  định video" của riêng mình (kiểu hộp chữ, dạng chữ, cỡ chữ, giọng,
  nhạc mặc định...). Thứ tự áp dụng: mặc định của user › mặc định
  của team. Màn hình Cài đặt phải ghi rõ đang sửa mặc định của tài
  khoản nào. Mặc định của team giữ vai trò bộ khởi tạo cho tài khoản
  mới.
- **B2. Lọc theo người.** Danh sách Page có bộ lọc "Trang của tôi /
  Tất cả"; Fanpage gắn được chủ sở hữu (owner = tài khoản thành
  viên) — việc này phục vụ luôn mô hình tiền-riêng-theo-người đã
  chốt của team. Các màn hình chọn topic/Page khi tạo video và lên
  lịch cũng lọc/ưu tiên theo người đang đăng nhập.
- **B3. Giá trị mặc định theo user ở các form.** Tạo video, lên lịch
  đăng, gắn sản phẩm: tự chọn trước Page/topic/giọng/nhạc theo mặc
  định của user đó (hoặc lựa chọn gần nhất của chính user đó), thay
  vì để trống hoặc lấy lựa chọn của người khác.
- **Ngoài phạm vi:** không thay đổi quyền xem dữ liệu của nhau trong
  team (mọi người vẫn xem được việc của nhau khi cần); không đụng
  vào luồng đăng bài, đo số liệu và gắn affiliate hiện tại.

## Thứ tự đề xuất

Phần A làm và merge trước (nhỏ, độc lập, giải quyết nhu cầu chữ
thường ngay). Phần B làm sau, theo thứ tự B1 → B2 → B3, mỗi giai
đoạn một nhánh riêng và báo cáo riêng.

## Kết quả kiểm tra và lựa chọn của user (08/11)

Kiểm tra code ngày 08/11 cho thấy Fanpage **đã có** chủ sở hữu
(`fanpages.owner_id`, quyết định 2026-11-03, nút "Nhận Page này"); B2
không cần thêm cột chủ sở hữu.

1. Cảnh tiêu đề có tùy chọn "Dạng chữ" **riêng**, như cỡ chữ tiêu đề.
2. Lớp chữ trên cảnh **theo** dạng chữ của các cảnh.
3. Bỏ yêu cầu "viết hoa" tiêu đề trong prompt mặc định và phần mô tả
   định dạng đầu ra.
4. B1: mặc định của user là những gì user đó cài đặt; bỏ nút "Lấy
   theo mặc định nhóm" trên video.
5. B2: "topic của tôi" là các nhóm chủ đề của những Page mình sở hữu.
6. B3: lựa chọn gần nhất lưu trên server theo tài khoản.
7. Brief này đi cùng PR của phần A.
