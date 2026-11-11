# Brief: Gắn thẻ (tags) cho Kho tư liệu — tra cứu ảnh theo động tác/vùng khớp/bối cảnh

Repo: Reels-Studio · Nhánh: `feat/media-library-upgrade`
Đọc trước: `AGENTS.md`, các file trong `docs/decisions/`, và brief `docs/specs/media-library-upgrade/brief.md`.
**Điều kiện bắt đầu: làm cùng đợt với brief nâng cấp kho, trên CÙNG nhánh `feat/media-library-upgrade` (user chốt 11/11 — không tách nhánh riêng, không chờ merge). Nếu phần thư mục của brief nâng cấp kho chưa xong trong nhánh thì làm phần thư mục trước, rồi nối tiếp brief này trong cùng nhánh.**

## Bối cảnh (đã kiểm chứng 11/11/2026)

- Kho tư liệu hiện có trường `folder` (text) và MCP `list_media` lọc theo `folder`/`kind`, tìm `query` theo tên file. Không có trường mô tả hay thẻ nào.
- Ngày 11/11 đã nạp ngân hàng 42 ảnh minh họa Ông Khỏe – Bà Vui (media id 25–66) vào 8 thư mục theo chủ đề cho page Già Mà Khỏe. Việc khớp cảnh → ảnh hiện dựa vào thư mục + tên file + một file bản đồ ảnh ngoài hệ thống (`MANIFEST.md` phía vận hành). Tên file không chứa đủ thông tin (bối cảnh, vùng khớp, loại cảnh mở đầu/CTA/lưu ý), nên tra cứu vẫn phải đọc thêm tài liệu ngoài.
- Mục tiêu của brief: đưa thông tin khớp đó VÀO trong kho dưới dạng thẻ có cấu trúc, để cả người dùng trên web lẫn job dựng qua MCP đều tra cứu xác định được: cho tôi ảnh [động tác X] + [vùng Y] + [bối cảnh Z].

## Phạm vi

### A. Dữ liệu

1. Thêm trường `tags` cho `MediaItem`: danh sách chuỗi, mặc định rỗng, không bắt buộc.
2. Chuẩn hoá thẻ ở phía server khi lưu: chữ thường, tiếng Việt **không dấu**, từ ghép nối bằng `-` (ví dụ `xoay-co`, `co-vai-gay`, `buoi-toi`), cắt khoảng trắng thừa, loại trùng. Đầu vào sai định dạng (có dấu, có khoảng trắng) phải được chuẩn hoá thay vì báo lỗi, trừ thẻ rỗng.
3. Không đổi hành vi của `folder`; thẻ và thư mục là hai lớp độc lập.

### B. Giao diện web (trang Kho tư liệu)

1. Mỗi thẻ ảnh hiển thị các thẻ của nó dạng chip nhỏ dưới tên file.
2. Sửa thẻ: trên thẻ ảnh có hành động sửa thẻ (ô nhập dạng chip, có gợi ý tự hoàn thành từ vốn thẻ đang có trong kho — ưu tiên chọn thẻ có sẵn hơn gõ thẻ mới; vẫn cho tạo thẻ mới).
3. Chọn nhiều ảnh → thanh công cụ có "Thêm thẻ" và "Gỡ thẻ" áp dụng cho cả loạt.
4. Form tải lên: thêm ô thẻ tuỳ chọn (cùng cơ chế chip/gợi ý như trên).
5. Lọc theo thẻ: cạnh bộ lọc thư mục hiện có, thêm lọc theo một hoặc nhiều thẻ (chọn nhiều thẻ = ảnh phải có ĐỦ các thẻ đã chọn). Kết hợp được với lọc thư mục (giao nhau).

### C. API / MCP

1. `list_media` thêm tham số `tags` (danh sách, phân tách bằng dấu phẩy): chỉ trả ảnh có đủ mọi thẻ trong danh sách. Tham số này kết hợp được với `folder` và `kind` hiện có.
2. Tham số `query` hiện có: mở rộng để khớp cả vào thẻ (ngoài tên file như hiện tại).
3. Mỗi item trong response của `list_media` trả kèm `tags` của nó.
4. Nếu bề mặt API có endpoint sửa media (từ brief nâng cấp kho), cho phép cập nhật `tags` qua đó; nếu chưa có, thêm endpoint sửa thẻ tối thiểu phục vụ giao diện web ở mục B — không mở thêm tool MCP ghi mới trong brief này.

### D. Nạp sẵn thẻ cho 42 ảnh Già (backfill một lần)

Viết script/seed một lần (chạy tay, có log rõ ràng, chạy lại không nhân đôi) gán thẻ cho 42 ảnh hiện có **theo tên file**, đúng bảng ở Phụ lục. Ảnh không khớp tên nào trong bảng → bỏ qua và ghi log. Đây là dữ liệu vận hành thật, không phải dữ liệu mẫu.

## Ngoài phạm vi

- Không làm gợi ý ảnh tự động theo nội dung cảnh (đó là giai đoạn sau, khi vốn thẻ đã ổn định).
- Không dùng AI tự sinh thẻ.
- Không đổi mô hình thư mục, không đổi quyền truy cập.
- Không đụng luồng dựng/đăng video.

## Tiêu chí nghiệm thu

1. Chuẩn hoá thẻ: lưu `Xoay Cổ`, ` xoay-co `, `XOAY-CO` cho cùng một kết quả `xoay-co`; thẻ trùng bị khử.
2. Sửa thẻ trên 1 ảnh và trên loạt nhiều ảnh hoạt động; chip hiển thị đúng sau khi tải lại trang.
3. Lọc web: chọn 2 thẻ → chỉ hiện ảnh có đủ cả 2; kết hợp thêm thư mục → giao nhau đúng.
4. MCP: `list_media` với `tags=xoay-co,sofa` chỉ trả ảnh có cả hai thẻ; `query` khớp được theo thẻ; response có trường `tags`.
5. Backfill: sau khi chạy seed, 42 ảnh ở Phụ lục có đúng bộ thẻ như bảng (kiểm chứng bằng `list_media` theo vài thẻ đại diện: `thang-bang` → 4 ảnh; `cta` → 2 ảnh; `xoa-bop` → 2 ảnh; `tu-the-sai` → đúng 1 ảnh gia-dibo-02-gu-lung).
6. Test tự động theo thông lệ repo cho: chuẩn hoá thẻ, lọc theo thẻ (API), seed không nhân đôi khi chạy lại. Báo số test pass/fail.
7. Ghi quyết định mới vào `docs/decisions/` (một file riêng): mô hình thẻ (chuẩn hoá không dấu), quan hệ thẻ ↔ thư mục, và việc seed theo tên file là một lần.

## Ràng buộc làm việc

- Không dùng subagent.
- Làm trên nhánh `feat/media-library-upgrade` (cùng nhánh với brief nâng cấp kho), TDD/fake-service test như thông lệ repo.
- Báo cáo 3 phần: Done / Verified / Remaining risks.
- Không tự commit hay merge — chờ user duyệt.

## Phụ lục: Bảng thẻ nạp sẵn cho 42 ảnh (theo tên file)

| file | tags |
|---|---|
| gia-goi-01-mo-dau.webp | ca-hai, phong-khach, ngoi-ghe, mo-dau, nam-tay |
| gia-goi-02-nang-chan-thang.webp | ba, phong-khach, ngoi-ghe, nang-chan-thang, goi, dui-truoc |
| gia-goi-03-truot-got.webp | ba, phong-khach, ngoi-ghe, truot-got, goi |
| gia-goi-04-ep-goi-xuong-khan.webp | ong, phong-khach, ngoi-ghe, ep-goi, khan, goi, dui-truoc |
| gia-goi-05-nhac-got-chan.webp | ba, phong-khach, ngoi-ghe, nhac-got, bap-chan, co-chan |
| gia-goi-06-xoay-co-chan.webp | ong, phong-khach, ngoi-ghe, xoay-co-chan, co-chan |
| gia-goi-07-nghi-uong-nuoc.webp | ca-hai, phong-khach, ngoi-ghe, nghi, uong-nuoc, luu-y |
| gia-goi-08-cta-nam-tay.webp | ca-hai, phong-khach, ngoi-ghe, cta, nam-tay |
| gia-goi-09-xoa-bop-goi.webp | ba, phong-ngu, ngoi-me-giuong, xoa-bop, goi, buoi-toi |
| gia-goi-10-chuom-am-goi.webp | ong, phong-ngu, ngoi-ghe, chuom-am, khan, goi, buoi-toi |
| gia-ngu-01-mo-dau.webp | ca-hai, phong-ngu, ngoi-tren-giuong, mo-dau, buoi-toi |
| gia-ngu-02-tho-bung.webp | ong, phong-ngu, nam-ngua, tho-bung, hoi-tho |
| gia-ngu-03-om-goi.webp | ong, phong-ngu, nam-ngua, om-goi, lung-duoi, hong |
| gia-ngu-04-van-minh.webp | ba, phong-ngu, nam-ngua, van-minh, cot-song |
| gia-ngu-05-gac-chan-len-goi.webp | ba, phong-ngu, nam-ngua, gac-chan, thu-gian |
| gia-ngu-06-tha-long.webp | ca-hai, phong-ngu, nam, tha-long, toan-than |
| gia-ngu-07-ngoi-me-giuong.webp | ong, phong-ngu, ngoi-me-giuong, luu-y, chong-mat |
| gia-ngu-08-cta.webp | ca-hai, phong-ngu, ngoi-tren-giuong, cta, vay-tay |
| gia-ngu-09-xoay-co.webp | ong, phong-ngu, ngoi-me-giuong, xoay-co, co |
| gia-ngu-10-nhun-vai.webp | ba, phong-ngu, ngoi-me-giuong, nhun-vai, vai |
| gia-ngu-11-vuon-tay.webp | ong, phong-ngu, ngoi-me-giuong, vuon-tay, vai, dan-tay |
| gia-ngu-12-xoay-co-tay-co-chan.webp | ba, phong-ngu, ngoi-me-giuong, xoay-co-tay, xoay-co-chan, co-tay, co-chan |
| gia-sofa-01-xoay-co.webp | ong, sofa, ngoi, xoay-co, co, xem-tivi, buoi-toi |
| gia-sofa-02-nhun-vai.webp | ba, sofa, ngoi, nhun-vai, vai, xem-tivi, buoi-toi |
| gia-sofa-03-xoay-co-tay.webp | ong, sofa, ngoi, xoay-co-tay, co-tay, xem-tivi, buoi-toi |
| gia-sofa-04-vuon-tay.webp | ba, sofa, ngoi, vuon-tay, vai, dan-tay, xem-tivi, buoi-toi |
| gia-dung-01-nhon-chan-vin-ghe.webp | ong, phong-khach, dung, vin-ghe, nhon-chan, bap-chan, thang-bang |
| gia-dung-02-dung-mot-chan.webp | ba, phong-khach, dung, vin-ghe, dung-mot-chan, thang-bang |
| gia-dung-03-buoc-ngang.webp | ong, phong-khach, dung, vin-ghe, buoc-ngang, hong, thang-bang |
| gia-dung-04-got-cham-mui.webp | ba, phong-khach, dung, vin-ghe, got-cham-mui, tandem, thang-bang |
| gia-lung-01-om-mot-goi.webp | ong, phong-ngu, nam-ngua, om-mot-goi, lung-duoi |
| gia-lung-02-nam-nghieng-om-goi-om.webp | ba, phong-ngu, nam-nghieng, om-goi-om, lung, thu-gian |
| gia-lung-03-tuong-truot.webp | ong, tuong, dung, truot-tuong, lung, dui |
| gia-lung-04-tuong-vuon-tay.webp | ba, tuong, dung, vuon-tay, lung-tren, vai |
| gia-lung-05-tuong-ep-lung.webp | ba, tuong, dung, ep-lung, lung-duoi, chong-hong |
| gia-lung-06-tuong-nang-goi.webp | ong, tuong, dung, vin-tuong, nang-goi, hong |
| gia-trinho-01-cham-cheo.webp | ong, phong-khach, dung, cham-cheo, phoi-hop, tri-nho |
| gia-trinho-02-dem-ngon-tay.webp | ba, phong-khach, ngoi-ban, dem-ngon-tay, ngon-tay, tri-nho |
| gia-tay-01-nam-mo.webp | ong, phong-khach, ngoi-ghe, nam-mo, ban-tay, ngon-tay, khop-tay |
| gia-tay-02-xoa-bop-ngon.webp | ba, phong-khach, ngoi-ghe, xoa-bop, ngon-tay, khop-tay |
| gia-dibo-01-tu-the-dung.webp | ca-hai, vuon, di-bo, tu-the-dung, toan-than |
| gia-dibo-02-gu-lung.webp | ong, vuon, di-bo, tu-the-sai, gu-lung, canh-bao |
