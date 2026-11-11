# Brief: Nâng cấp Kho tư liệu — quản lý thư mục + tư liệu theo chủ đề

Repo: Reels-Studio · Nhánh: `feat/media-library-upgrade`
Đọc trước: `AGENTS.md`, các file trong `docs/decisions/` (quy ước: quyết định mới = file mới trong `docs/decisions/`, không append vào file cũ).

## Bối cảnh (đã kiểm chứng trên production ngày 11/11/2026)

Kho tư liệu (`/media`) hiện tổ chức ảnh bằng nhãn thư mục gán lúc tải lên. Ngày 11/11 đã nạp ngân hàng ảnh minh họa Ông Khỏe – Bà Vui cho page Già Mà Khỏe và tách thành 3 thư mục theo chủ đề: `Gia - Goi khop` (8 ảnh), `Gia - Giac ngu` (8 ảnh), `Gia - Co vai gay` (4 ảnh). Quá trình đó bộc lộ các thiếu sót sau — tất cả đã kiểm chứng trực tiếp trên giao diện thật:

1. **Không đổi được thư mục của ảnh đã nạp.** Bấm vào ảnh chỉ có nút Xoá; không có xem chi tiết, không có sửa/chuyển thư mục. Muốn tách thư mục phải tải lại toàn bộ rồi xóa bản cũ — và mỗi lần tải lại, `media id` bị đổi (đợt 11/11: id 5–24 → 25–44), làm mọi tham chiếu theo id (ví dụ trong hướng dẫn vận hành của job dựng qua MCP) bị stale.
2. **Không quản lý được thư mục.** Không đổi tên thư mục, không xóa thư mục; thư mục chỉ tồn tại như chuỗi text gõ tay ở form tải lên (dễ gõ lệch tên → sinh thư mục trùng nghĩa).
3. **Có lọc theo thư mục nhưng chọn thư mục bằng text tự do.** Bộ lọc "Lọc theo thư mục" đã có và hoạt động; điểm thiếu là khâu chọn thư mục khi tải lên/quản lý vẫn là ô text tự do thay vì dropdown chọn từ danh sách có sẵn.
4. **Chủ đề trong Kho kiến thức không có view tư liệu riêng.** Người dùng muốn mở một chủ đề là thấy ngay tư liệu của chủ đề đó. ĐÃ CHỐT hướng thiết kế: **một kho chung duy nhất**, thư mục là lớp tổ chức; trang chủ đề hiển thị view lọc sẵn theo thư mục của chủ đề — KHÔNG tách kho riêng theo chủ đề (tránh trùng lặp ảnh dùng chung giữa các chủ đề, tránh phải sửa nhiều bản của cùng một ảnh).

Hành vi đúng hiện tại cần giữ nguyên: xóa ảnh khỏi kho không làm hỏng cảnh đã dùng ảnh đó (app đã báo rõ "Cảnh đã dùng tư liệu này vẫn giữ bản sao của nó"); lọc theo thư mục qua web và qua MCP (`list_media` với tham số `folder`) đều hoạt động.

## Phạm vi

### A. Quản lý thư mục trong Kho tư liệu

1. **Chuyển thư mục cho ảnh đã có** (quan trọng nhất):
   - Trên mỗi thẻ ảnh: thêm hành động "Chuyển thư mục" mở dropdown gồm: các thư mục hiện có (kèm số lượng ảnh), "Thư mục mới…" (nhập tên mới), và "Không thư mục" (đưa về gốc).
   - Chọn nhiều ảnh (checkbox) → thanh công cụ có "Chuyển thư mục" áp dụng cho cả loạt.
   - Chuyển thư mục CHỈ đổi nhãn `folder` của bản ghi — **media id và file vật lý không đổi**, để tham chiếu từ MCP/cảnh không bị gãy.
2. **Đổi tên thư mục**: một thao tác đổi nhãn cho mọi ảnh đang mang thư mục đó; cập nhật ngay danh sách thư mục ở bộ lọc.
3. **Xóa thư mục**: chỉ gỡ nhãn — ảnh chuyển về "Không thư mục", KHÔNG xóa ảnh. Có hộp thoại xác nhận ghi rõ số ảnh bị ảnh hưởng.
4. **Dropdown chọn thư mục ở mọi nơi chọn thư mục** (form tải lên + hành động chuyển): select liệt kê thư mục hiện có kèm số lượng, cho phép tạo mới ngay trong dropdown (gõ tên mới → tạo). Thay ô text tự do hiện tại, nhưng dữ liệu cũ (chuỗi folder) không đổi mô hình.

### B. Tư liệu theo chủ đề trong Kho kiến thức

1. Thêm trường liên kết trên `KnowledgeTopic`: `media_folder` (nullable) — tên thư mục trong kho chung mà chủ đề đó dùng. Mặc định null = chưa liên kết.
2. Trong trang chi tiết của một chủ đề (Kho kiến thức), thêm mục/tab **"Tư liệu"**:
   - Nếu đã liên kết thư mục: hiển thị lưới ảnh của kho chung lọc đúng thư mục đó (tái dùng component lưới của trang `/media`), kèm nút "Tải ảnh vào thư mục này" (form tải với thư mục khóa sẵn = thư mục của chủ đề) và nút mở trang kho đầy đủ tại đúng bộ lọc đó.
   - Nếu chưa liên kết: trạng thái trống có nút "Liên kết thư mục" mở dropdown chọn thư mục có sẵn hoặc tạo mới (ghi vào `media_folder`).
   - Một thư mục có thể được liên kết bởi tối đa một chủ đề tại một thời điểm (validate khi lưu: báo rõ nếu thư mục đã thuộc chủ đề khác).
3. Không thay đổi mô hình lưu trữ của `MediaItem` ngoài việc giữ nguyên trường folder hiện có; không tạo bảng kho riêng theo chủ đề.

### C. MCP (chỉ khi rẻ và an toàn)

- Giữ nguyên bề mặt tool hiện tại. Nếu thuận tay: `list_media` trả thêm danh sách thư mục kèm số lượng trong cùng response (hiện đã có `folders` — kiểm tra và giữ nguyên nếu đã đủ). Không thêm tool ghi mới trong brief này.

## Ngoài phạm vi

- Không đổi quyền truy cập/phân quyền theo thư mục.
- Không di trú dữ liệu: 3 thư mục Già hiện có giữ nguyên tên và nội dung; việc liên kết chúng vào chủ đề "Già Mà Khỏe – Dưỡng sinh sau 50" do user tự bấm sau khi tính năng lên (các thư mục theo trụ của cùng một chủ đề: liên kết thư mục cha theo quy ước tiền tố là việc của giai đoạn sau, brief này chỉ cần liên kết 1 chủ đề ↔ 1 thư mục chạy đúng).
  - Ghi chú: thực tế một chủ đề có nhiều thư mục theo trụ (Già có 3). Nếu việc hỗ trợ tiền tố (chủ đề liên kết một tiền tố, view Tư liệu hiện mọi thư mục bắt đầu bằng tiền tố đó) rẻ hơn về lâu dài, đề xuất trong báo cáo trước khi làm — không tự mở rộng phạm vi.
- Không đụng vào luồng dựng/đăng video, không đổi hành vi xóa ảnh (cảnh giữ bản sao).

## Tiêu chí nghiệm thu

1. Chuyển 1 ảnh và chuyển loạt nhiều ảnh sang thư mục khác: id không đổi, file không tải lại, bộ lọc và số lượng thư mục cập nhật đúng.
2. Đổi tên thư mục: mọi ảnh mang thư mục cũ chuyển sang tên mới; `media_folder` của chủ đề đang liên kết (nếu trùng tên cũ) được cập nhật theo hoặc bị chặn kèm thông báo rõ — chọn một hành vi và ghi vào decision.
3. Xóa thư mục: ảnh về gốc, không mất ảnh nào.
4. Form tải lên: chọn thư mục từ dropdown (có sẵn + tạo mới), không còn ô text tự do.
5. Trang chủ đề: tab Tư liệu hiện đúng ảnh của thư mục đã liên kết; tải ảnh từ tab này vào đúng thư mục; chủ đề chưa liên kết hiện trạng thái trống + nút liên kết.
6. Kiểm chứng bằng test tự động theo thông lệ repo (fake-service cũng được): các case 1–5 ở mức API/service; chạy test liên quan tới media và knowledge topics, báo số test pass/fail.
7. Ghi quyết định mới vào `docs/decisions/` (một file riêng, đặt tên theo ngày + slug), nêu rõ: mô hình một-kho-chung + thư mục, hành vi đổi tên thư mục đối với liên kết chủ đề, và id ổn định khi chuyển thư mục.

## Ràng buộc làm việc

- Không dùng subagent.
- Làm trên nhánh `feat/media-library-upgrade`, TDD/fake-service test như thông lệ repo.
- Báo cáo 3 phần: Done / Verified / Remaining risks.
- Không tự commit hay merge — chờ user duyệt.
