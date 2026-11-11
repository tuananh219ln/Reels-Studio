# Brief: Hiển thị cây thư mục cha–con trong Kho tư liệu

Repo: Reels-Studio · Nhánh: `feat/media-folder-tree` (tạo từ main sau khi nhánh feat/media-library-upgrade đã merge/deploy)
Đọc trước: `AGENTS.md`, các file trong `docs/decisions/` (đặc biệt quyết định về mô hình thư mục/thẻ của đợt nâng cấp kho), brief `docs/specs/media-library-upgrade/brief.md` và `docs/specs/media-tags/brief.md`.

## Bối cảnh (đã kiểm chứng trên production 11/11/2026)

- Mô hình dữ liệu hiện tại: trường `folder` của tư liệu là một chuỗi đường dẫn, thư mục con ngăn cách bằng `/` (ví dụ `Già Mà Khỏe/Goi khop`). Đổi tên/ di chuyển thư mục đã hoạt động; chủ đề kiến thức liên kết theo tiền tố thư mục cha (chủ đề Già Mà Khỏe đã liên kết thư mục cha `Già Mà Khỏe` (tiền tố ban đầu là `Gia`, đã đổi sang đúng tên page ngày 11/11/2026) và thấy đủ 42 tư liệu của 8 thư mục con).
- Vấn đề: mọi danh sách thư mục trên giao diện hiện hiển thị PHẲNG — bộ lọc thư mục ở trang Kho tư liệu liệt kê 8 dòng `Gia/Goi khop`, `Gia/Giac ngu`, … rời nhau, không có nút thư mục cha gập/mở, không thấy được quan hệ cha–con. Người dùng không ưng: cần nhìn thấy cây — thư mục cha (ví dụ `Già Mà Khỏe`) chứa các thư mục con bên trong.
- Brief này CHỈ sửa lớp hiển thị và ngữ nghĩa lọc theo cây; dữ liệu lưu (chuỗi `folder`) không đổi, không cần migration.

## Phạm vi

### A. Cây thư mục ở bộ lọc trang Kho tư liệu (/media)

1. Bộ lọc thư mục hiển thị dạng cây: mỗi tiền tố trước dấu `/` đầu tiên là một nút cha, gập/mở được (mặc định: mở các nút cha đang chứa thư mục/tư liệu khớp bộ lọc khác nếu có; lần đầu vào trang thì mở hết cũng được — chọn một và ghi vào quyết định).
2. Mỗi nút hiển thị số tư liệu: nút con = số tư liệu trong đúng thư mục đó; nút cha = TỔNG số tư liệu của nó và mọi thư mục con cháu.
3. Chọn một nút = lọc theo tiền tố theo đoạn đường dẫn:
   - Chọn nút cha `Già Mà Khỏe` → hiện mọi tư liệu có folder là `Già Mà Khỏe` hoặc bắt đầu bằng `Già Mà Khỏe/`.
   - Chọn nút con `Già Mà Khỏe/Lung` → folder là `Già Mà Khỏe/Lung` hoặc bắt đầu bằng `Già Mà Khỏe/Lung/` (nếu sau này có cháu sâu hơn).
   - Tư liệu nằm ngay ở thư mục cha (folder đúng bằng `Già Mà Khỏe`) được tính vào nút cha và hiện khi chọn nút cha.
4. Vẫn giữ lựa chọn "Tất cả thư mục" như hiện tại. Cây kết hợp đúng với các bộ lọc còn lại (thẻ, loại, tìm kiếm) theo phép giao.
5. Hỗ trợ độ sâu tùy ý (tách theo mọi dấu `/`), không khóa cứng 2 tầng.

### B. Áp cùng cách hiển thị cây ở mọi nơi chọn thư mục

1. Ô chọn thư mục trong form tải lên (dropdown gợi ý thư mục hiện có).
2. Ô chọn thư mục đích khi đổi tên/di chuyển thư mục.
3. Ô "Liên kết thư mục" trong tab Tư liệu của chủ đề kiến thức (chọn nút cha phải hoạt động như liên kết tiền tố hiện tại — hành vi liên kết KHÔNG đổi, chỉ đổi cách hiển thị danh sách chọn).
4. Nhãn hiển thị của nút là đúng chuỗi đoạn đường dẫn (ví dụ nút cha hiện chữ `Già Mà Khỏe`, nút con hiện `Goi khop`) — không thêm cơ chế đặt tên hiển thị riêng trong brief này.

### C. Nút hành động trên cây (nếu làm được trong cùng đợt, không bắt buộc tách riêng)

- Nút cha cũng có các hành động thư mục hiện có (đổi tên) như nút con, áp cho toàn bộ tiền tố (đổi tên `Già Mà Khỏe` → mọi folder `Già Mà Khỏe/...` đổi theo). Nếu phần này chạm vào logic đổi tên hiện tại quá sâu, ghi rõ trong báo cáo là để lại và chỉ làm mục A+B.

## Ngoài phạm vi

- Không đổi mô hình dữ liệu, không đổi API/MCP (`list_media` giữ nguyên tham số folder/thẻ như hiện tại).
- Không thêm thư mục "ảo" hay bản ghi thư mục riêng.
- Không đụng luồng dựng/đăng video, không đụng thẻ.

## Tiêu chí nghiệm thu

1. Vào /media: bộ lọc hiện cây có nút cha `Già Mà Khỏe` (tổng 42) và 8 nút con với số đếm lần lượt 10/8/8/4/6/2/2/2 (theo dữ liệu production hiện tại); gập nút cha lại thì 8 nút con ẩn đi.
2. Chọn nút cha `Gia` → lưới hiện đủ 42 tư liệu; chọn nút con `Già Mà Khỏe/Thang bang` → đúng 4 tư liệu; chọn nút con rồi thêm lọc thẻ → giao nhau đúng.
3. Dropdown chọn thư mục ở form tải lên và ô liên kết thư mục của chủ đề đều hiện dạng cây; chọn nút cha trong ô liên kết vẫn liên kết được và tab Tư liệu hiện đúng tổng số.
4. Test tự động: hàm dựng cây từ danh sách folder phẳng (gồm trường hợp: folder không có `/`, folder sâu 3 tầng, tư liệu nằm ngay ở thư mục cha, tên thư mục trùng tiền tố một phần kiểu `Gia` vs `Gian` trên dữ liệu test tự tạo — nút cha `Gia` KHÔNG được nuốt `Gian/...`); test ngữ nghĩa lọc theo tiền tố đoạn. Báo số test pass/fail.
5. Ghi quyết định mới vào `docs/decisions/` (một file riêng): hiển thị cây là lớp trình bày trên chuỗi đường dẫn, ngữ nghĩa chọn nút = lọc tiền tố theo đoạn.

## Ràng buộc làm việc

- Không dùng subagent.
- TDD/fake-service test như thông lệ repo.
- Báo cáo 3 phần: Done / Verified / Remaining risks.
- Không tự commit hay merge — chờ user duyệt.
