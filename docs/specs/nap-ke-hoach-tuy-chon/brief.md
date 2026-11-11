# Brief Reels Studio — Nạp kế hoạch có lựa chọn chế độ (ghi đè toàn bộ / thêm vào cuối ngày / thêm vào ngày trống tiếp theo / thay thế các ngày có trong file)

> Soạn 11/11/2026 theo quyết định của user (chủ sản phẩm).
> Cách làm theo lệ của team: đọc AGENTS.md + docs/decisions.md
> trước; nhánh riêng; TDD (viết test trước); chạy đủ test api +
> web; báo cáo 3 phần theo AGENTS.md; không tự merge; chạy
> inline, không dùng subagent.
> Brief này cũng trả luôn yêu cầu "Nạp nối tiếp" đã nêu ngày
> 08/11 — đó chính là chế độ 3 bên dưới.

## Bối cảnh (sự cố thực tế dẫn tới brief)

Nạp file kế hoạch (tab Kế hoạch 30 ngày, nút "Nhập file") hiện
chỉ có MỘT hành vi: **ghi đè toàn bộ kế hoạch** theo đúng số
ngày trong file. Hệ quả gặp thật ngày 11/11 khi cần sửa 3 ô ý
tưởng (ngày 4, 7, 9) trong kế hoạch 14 ngày đang chạy:

- Muốn sửa lẻ 3 ngày cũng phải nạp lại cả file 14 ngày.
- Nếu lỡ nạp một file thiếu ngày, các ngày thiếu trống theo —
  rủi ro mất kế hoạch đang chạy chỉ vì một lần nạp vội.
- Muốn "gia hạn" kế hoạch thêm đợt ngày mới sau ngày 14 cũng
  không có đường nạp nối tiếp an toàn.

Dữ liệu đã sẵn sàng cho việc gộp: mỗi ngày trong kế hoạch chứa
được 1–10 ý tưởng (đã có từ đợt làm lại tab Kế hoạch), nên
"thêm ý tưởng vào một ngày đã có" không cần đổi cấu trúc dữ
liệu.

## Yêu cầu

Hộp thoại nạp file thêm **lựa chọn chế độ nạp** (4 chế độ),
người nạp chọn trước khi bấm xác nhận. Chế độ 1 là hành vi
hiện tại, giữ nguyên làm mặc định.

### Chế độ 1 — Ghi đè toàn bộ (hiện tại, không đổi)
Toàn bộ kế hoạch thay bằng nội dung file, theo số ngày trong
file. Giữ nguyên từng ly so với hiện nay.

### Chế độ 2 — Thêm vào cuối ngày (gộp theo số ngày)
Với mỗi ngày có trong file:
- Ngày tương ứng trong kế hoạch đang **trống** → điền ý tưởng
  của file vào ngày đó.
- Ngày tương ứng **đã có ý tưởng** → **thêm các ý tưởng của
  file vào cuối danh sách ý tưởng của ngày đó**, giữ nguyên
  thứ tự các ý tưởng cũ ở trước.
- Ngày không có trong file → không đụng tới.

### Chế độ 3 — Thêm vào ngày trống tiếp theo (nạp nối tiếp)
- Các ngày trong file được lấy theo thứ tự và điền lần lượt
  vào **các ngày đang trống gần nhất** của kế hoạch (ngày
  trống = ngày chưa có ý tưởng nào), bắt đầu từ ngày trống
  đầu tiên. Số ngày trong file không cần khớp số ngày trống
  còn lại nếu ít hơn.
- Trước khi áp dụng, nếu số ngày trống còn lại **ít hơn** số
  ngày trong file: hiện cảnh báo rõ "còn X ngày trống, file có
  Y ngày" và cho người nạp chọn Hủy hoặc Nạp phần vừa (điền
  đến khi hết ngày trống thì dừng) — không tự im lặng cắt.

### Chế độ 4 — Thay thế các ngày có trong file
(Bổ sung theo quyết định của user 11/11 16:10.)
Với mỗi ngày có trong file: **toàn bộ ý tưởng của ngày tương
ứng trong kế hoạch được thay bằng ý tưởng trong file**. Ngày
không có trong file → không đụng tới. Đây là chế độ dành cho
sửa lẻ (ví dụ nạp file chỉ gồm ngày 4, 7, 9 để thay đúng 3
ngày đó), thay cho việc phải ghi đè cả kế hoạch như hiện nay.
- Trước khi áp dụng, hộp thoại liệt kê rõ các ngày sẽ bị
  thay; ngày nào trong số đó **đã có video dựng từ ý tưởng
  hiện tại** thì gắn cảnh báo cạnh ngày đó để người nạp thấy
  trước khi xác nhận.
- Nạp kế hoạch không bao giờ xóa video đã dựng: video cũ của
  một ngày bị thay vẫn giữ nguyên trong thư viện video, chỉ
  là ý tưởng của ngày đó từ nay là ý tưởng mới.

### Quy tắc chung cho chế độ 2 và 3
- **Chống trùng:** một ý tưởng trong file có `topic` trùng
  khít với một ý tưởng đã có trong cùng ngày đích → bỏ qua ý
  tưởng đó, tính vào mục "trùng, đã bỏ qua" trong báo cáo nạp.
- **Báo cáo sau khi nạp** (mọi chế độ đều hiện): số ngày được
  điền mới, số ngày được thêm ý tưởng, số ý tưởng bị bỏ qua
  vì trùng, số ngày trong file không nạp được (nếu có). Nạp
  xong phải nhìn thấy ngay đã thay đổi những ngày nào.
- **Luật cho bên tiêu thụ kế hoạch** (job dựng sáng, các lượt
  chạy tự động, nút tạo video từ ý tưởng): khi một ngày có
  nhiều ý tưởng, luôn lấy **ý tưởng đầu tiên trong ngày chưa
  có video** để dựng; các ý tưởng thêm vào đóng vai trò phương
  án dự phòng, không tự dựng song song hai video cho cùng một
  ngày khi lịch chỉ có một suất đăng.

## Ngoài phạm vi
- Không đổi định dạng file nạp (vẫn `{"days":[{"day":N,
  "ideas":[{topic, pain_group, pain, hook}]}]}`).
- (Đã thay đổi 11/11 16:10: chế độ "thay thế các ngày có
  trong file" được chủ sản phẩm duyệt thêm — xem Chế độ 4.
  Dòng loại trừ cũ về chế độ này đã gỡ.)
- Không đổi hành vi của kế hoạch Già Mà Khỏe hay page khác —
  cơ chế nạp là của chung tab Kế hoạch, áp cho mọi nhóm như
  nhau.

## Nghiệm thu
- Nạp file đủ 14 ngày ở chế độ 1: kết quả giống hệt hiện nay.
- Kế hoạch đang có ngày 1–14; nạp file chỉ gồm ngày 4, 7, 9 ở
  chế độ 2: ngày 4, 7, 9 có thêm ý tưởng mới ở cuối danh sách
  của ngày; 11 ngày còn lại không đổi một ký tự; ngày 4, 7, 9
  vốn trống thì được điền mới.
- Cùng kế hoạch đó, nạp một file 5 ngày ở chế độ 3: 5 ngày
  trong file lần lượt vào ngày 15–19; ngày 1–14 nguyên vẹn.
- Nạp file có ý tưởng trùng topic với ý đã có trong ngày
  đích: ý trùng bị bỏ qua và báo cáo nạp ghi rõ.
- Chế độ 3 khi ngày trống không đủ: có cảnh báo trước, chọn
  Hủy thì kế hoạch không đổi gì.
- Kế hoạch đang có ngày 1–14; nạp file chỉ gồm ngày 4, 7, 9 ở
  chế độ 4: đúng 3 ngày đó thay toàn bộ ý tưởng theo file;
  11 ngày còn lại không đổi; hộp thoại liệt kê trước 3 ngày
  sẽ thay, và gắn cảnh báo nếu một ngày trong số đó đã có
  video; video đã dựng của các ngày bị thay vẫn còn nguyên.
- Ngày có 2 ý tưởng sau khi gộp: lượt dựng theo kế hoạch lấy
  ý tưởng đầu chưa có video; ý tưởng thứ hai không bị dựng
  trùng trong cùng ngày.
- Test tự động phủ: điền ngày trống, thêm cuối ngày có sẵn,
  chống trùng theo topic, nạp nối tiếp đúng thứ tự, tràn ngày
  trống, và hồi quy chế độ ghi đè. Chạy đủ test api + web,
  báo cáo 3 phần theo AGENTS.md.

## Việc kèm theo sau khi brief này được merge (user chốt 11/11 16:06)

Sau khi cơ chế nạp 3 chế độ chạy được trên production, phải
cập nhật LUÔN lệnh của job dựng sáng "rs-mcp-morning-build"
(chat "Dựng video mỗi sáng (MCP)") thêm luật lấy ý tưởng khi
một ngày có nhiều ý tưởng — hiện lệnh job CHƯA có luật này
(đã kiểm chứng 11/11: lệnh chỉ ghi "lấy ý tưởng của HÔM NAY"
và "ý tưởng đã có video thì bỏ qua"; list_plan_ideas trả ý
tưởng theo thứ tự ngày, trong ngày theo thứ tự lưu):

> Khi ngày hôm nay có nhiều ý tưởng: dựng Ý TƯỞNG ĐẦU TIÊN
> trong danh sách của ngày đó mà chưa có video. Các ý tưởng
> còn lại trong ngày là phương án dự phòng — không dựng
> trong cùng lượt, và ghi rõ trong báo cáo là ngày còn ý
> tưởng dự phòng chưa dùng.

Việc cập nhật lệnh job làm ở chat "Dựng video mỗi sáng
(MCP)" ngay sau khi tính năng nạp được xác nhận chạy trên
production, không làm trước (tránh lệnh nhắc tới cơ chế chưa
tồn tại).
