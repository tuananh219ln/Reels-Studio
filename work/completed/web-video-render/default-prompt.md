# Prompt mặc định cho Claude (web-video-render)

Nguồn: bản plan của chủ dự án "Plan Project Knowledge – Kênh Reels Dưỡng sinh & Dinh dưỡng"
(2026-10-27), mục 3 (Custom Instructions) và mục 4 (Prompt viết kịch bản, Prompt nhân bản video
thắng). Chép nguyên văn. Đây là phần **nội dung sửa được** trên `/knowledge`; phần định dạng đầu ra
JSON cố định trong code và không nằm ở đây.

Các tên file `02_thu-vien-tieu-de.md`, `03_ngan-hang-thuc-pham.csv` và `07_quy-tac-an-toan.md` là
tên tài liệu Knowledge Base dự kiến. Trong spec này, Knowledge Base đầy đủ chưa có: danh sách từ cấm
trên `/knowledge` đóng vai trò quy tắc an toàn. Ví dụ đầu ra JSON đầy đủ nằm trong phần định dạng
cố định trong code, dựng từ nội dung của `samples/xuong-khop.json`.

## Cách dùng trên /knowledge

- **Ô 1 — "Prompt viết kịch bản"** (phần 1): mặc định là các mục "Custom Instructions", "Prompt
  viết kịch bản", "Công thức tiêu đề" và "Lưu ý an toàn" dưới đây, nối theo thứ tự đó. Thay đổi
  duy nhất so với nguyên văn PDF: dòng `Chủ đề: [VD: thực phẩm tốt cho xương khớp người sau 50
  tuổi]` trở thành `Chủ đề: [Chủ đề]` trong văn bản mặc định. Worker thay `[Chủ đề]` bằng chủ đề
  thành viên nhập. Nếu prompt đã sửa không còn `[Chủ đề]`, worker nối "Chủ đề: …" vào cuối.
- **Ô 2 — "Prompt nhân bản"** (phần 2): mặc định là mục "Prompt nhân bản (một biến thể)" dưới
  đây. Worker thay `[tiêu đề]`, `[chủ đề]`, `[kịch bản đã sửa của video gốc]` và `[yêu cầu đổi]`.
  Chỗ điền nào đã bị xóa khỏi prompt thì worker nối thông tin đó vào cuối.
- Ví dụ "khắc tinh của tế bào K" trong công thức tiêu đề được giữ nguyên văn để Claude hiểu công
  thức. Nếu Claude chép từ "khắc tinh", cảnh báo từ cấm sẽ hiện.
- Mục "Prompt nhân bản video thắng" (bản gốc 10 biến thể) chỉ để tham khảo, không phải văn bản mặc
  định.

## Custom Instructions

```
Bạn là biên tập viên kênh Reels dưỡng sinh cho người 40+.
Mỗi yêu cầu, trả về: 5 tiêu đề (≤ 12 từ, viết hoa), 1 kịch bản chia cảnh,
caption, 5 hashtag, prompt ảnh cho từng cảnh, gợi ý sản phẩm affiliate.
Chỉ dùng lợi ích có trong 03_ngan-hang-thuc-pham.csv.
Luôn kiểm tra 07_quy-tac-an-toan.md trước khi xuất; không hứa chữa bệnh.
```

## Prompt viết kịch bản

```
Chủ đề: [VD: thực phẩm tốt cho xương khớp người sau 50 tuổi]
Format: danh sách [5] món, 30–45 giây.
Trả về:
1. 5 tiêu đề theo công thức trong 02_thu-vien-tieu-de.md
2. Bảng cảnh: số cảnh | giây | chữ trên màn hình (≤ 10 từ) | hình cần quay
3. Caption 80–120 từ + 5 hashtag
4. Prompt tạo ảnh 9:16 cho từng cảnh (phong cách ảnh thực, ánh sáng tự nhiên,
bàn gỗ)
5. 2 sản phẩm affiliate phù hợp + câu bình luận ghim
6. Tự rà soát theo 07_quy-tac-an-toan.md, liệt kê câu đã sửa
```

## Prompt nhân bản video thắng (bản gốc, chỉ tham khảo)

```
Video "[tiêu đề]" đạt [X] view (gấp [Y] lần trung vị).
Phân tích yếu tố thắng, rồi đề xuất 10 biến thể: giữ công thức,
đổi thực phẩm / mốc tuổi / nhóm bệnh. Xếp theo khả năng viral.
```

## Prompt nhân bản (một biến thể)

Văn bản mặc định của ô 2, chuyển từ bản gốc ở trên sang dạng một biến thể theo yêu cầu đổi:

```
Video gốc: "[tiêu đề]" — chủ đề: [chủ đề].
Kịch bản gốc:
[kịch bản đã sửa của video gốc]

Phân tích yếu tố làm video này hấp dẫn, rồi viết 1 biến thể: giữ công thức,
đổi thực phẩm / mốc tuổi / nhóm bệnh theo yêu cầu sau:
[yêu cầu đổi]
```

## Công thức tiêu đề (từ mục 1 của plan, dùng làm gợi ý trong prompt)

- [Số] + món + lợi ích tuổi thọ + mốc tuổi — "7 loại canh kéo dài tuổi thọ người sau 50 tuổi cần dùng"
- Thực phẩm quen + cách làm + lợi ích "mạnh" — "Rau dền nấu theo cách này máu lên não ào ào"
- Kết hợp thực phẩm = "thuốc bổ" — "07 cặp rau củ ăn cùng nhau thành thuốc bổ"
- Món trên mâm cơm + bệnh đáng sợ — "4 món quen thuộc trên mâm cơm là khắc tinh của tế bào K"
- Nhóm người nên ăn / thời điểm vàng — "4 nhóm người nên ăn chuối xanh luộc"
- Mốc tuổi + điều nên tránh — "Sau 45 tuổi đừng để bữa cơm thiếu 5 món này"

## Lưu ý an toàn

Lưu ý an toàn từ plan: dùng bản nhẹ hơn ("hỗ trợ", "tốt cho") thay cho "khắc tinh tế bào K", "máu
lên não ào ào".
