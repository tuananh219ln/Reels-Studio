# Prompt giao Claude Code — Giai đoạn 1: Tìm ảnh Pixabay trên web UI

> Dán toàn bộ phần dưới đường kẻ vào Claude Code đang mở tại thư mục gốc repo
> Reels-Studio. Lập ngày 2026-10-31.
>
> **Model khi chạy:** Sonnet 5.5, effort medium (đúng công thức đang dùng cho gói
> Pro $20). Việc này đã có brief và hợp đồng API rõ ràng, thuần thi công giao
> diện — không cần Opus. Chỉ nâng effort lên high khi kẹt cùng một lỗi qua 2–3
> vòng sửa vẫn không xong; xong việc thì hạ về medium.

---

Bạn đang làm việc trong repo Reels-Studio. Trước khi code, hãy đọc `AGENTS.md`,
`docs/decisions.md`, `docs/architecture.md` (mục Web App — Scenes) và brief tại
`docs/specs/ai-scene-images/brief.md`. Việc này CHỈ làm **Giai đoạn 1** của brief đó.

## Ràng buộc cứng

- Làm inline trong session này, TUYỆT ĐỐI không spawn subagent.
- Chỉ sửa phía web (`web/`). KHÔNG sửa backend (`api/`, `worker/`): cả 3 endpoint
  cần thiết đã có sẵn. Nếu bạn cho rằng backend thiếu gì đó, đừng tự sửa — ghi rõ
  vào báo cáo cuối và dừng phần đó lại.
- Không đọc, không sửa file `.env`. Không gọi API thật trong test (dùng fake Pixabay
  sẵn có trong `api/scripts/fake_services.py` / hạ tầng E2E hiện tại).
- Không đụng vào production. Test tay chỉ trên local (web :3000, api :8000).
- Tạo branch riêng theo quy ước repo, không commit vào `main`, không tự merge.

## Bối cảnh

Video mới sinh kịch bản xong thì các cảnh chưa có ảnh, thành viên phải upload tay.
Phía api đã có sẵn 3 endpoint Pixabay nhưng web UI chưa có nút nào gọi chúng. Việc
của bạn là đưa chúng lên thẻ cảnh trong trang sửa video. Hãy tự kiểm chứng lại hợp
đồng dưới đây trong `api/src/reels_api/routes_videos.py` trước khi dùng:

- `POST /scenes/{scene_id}/find-image` — không có body. Tự tìm 1 ảnh theo
  `keywords` đã lưu của cảnh và lưu vào cảnh. Cảnh đã có ảnh Pixabay thì gọi lại sẽ
  xoay sang ảnh khác. Lỗi: cảnh chưa có keywords → "Hãy nhập từ khóa tìm ảnh
  trước"; hết ảnh khác → 404 "Không tìm thấy ảnh khác, hãy đổi từ khóa"; Pixabay
  lỗi → 502 kèm thông điệp tiếng Việt.
- `GET /scenes/{scene_id}/pixabay?q=<từ khóa>` — `q` là bắt buộc. Trả
  `{keyword, hits: [{url, preview}]}`. `preview` là thumbnail chỉ để hiển thị;
  `url` là địa chỉ ảnh gốc.
- `POST /scenes/{scene_id}/pixabay` — body `{keyword, url}`. Server tự kiểm tra
  `url` có thuộc kết quả tìm của `keyword` đó không rồi mới tải bản gốc về lưu.
  Khi chọn ảnh trong lưới, phải gửi lại đúng `keyword` đã dùng để tìm.

## Yêu cầu chức năng

Trên thẻ của MỌI cảnh trong trang sửa video (kể cả cảnh tiêu đề):

1. **Nút "Chọn từ Pixabay"** (đây là luồng chính): mở panel chọn ảnh ngay trong
   thẻ cảnh hoặc modal theo phong cách Ant Design sẵn có của trang.
   - Ô từ khóa điền sẵn bằng từ khóa đầu tiên trong `keywords` của cảnh, sửa được;
     đổi từ khóa thì tìm lại.
   - Lưới thumbnail dùng trường `preview`, hiển thị toàn bộ kết quả trả về, lưới
     co giãn theo màn hình và dùng được trên điện thoại (không cuộn ngang bị khuất
     như các bảng đang bị phàn nàn trong backlog).
   - Bấm vào một ảnh → gọi `POST /scenes/{id}/pixabay` với đúng `{keyword, url}` →
     preview của cảnh cập nhật thành ảnh vừa chọn, panel đóng lại.
2. **Nút nhanh "Tìm ảnh"**: gọi `POST /scenes/{id}/find-image` cho lúc không cần
   chọn kỹ. Nếu cảnh đã có ảnh nguồn Pixabay, nhãn nút đổi thành "Tìm ảnh khác".
3. Trạng thái loading riêng cho từng cảnh (bấm ở cảnh này không khoá cả trang).
   Mọi lỗi đều hiện NGUYÊN thông điệp tiếng Việt từ api, không nuốt lỗi, không
   hiện thông điệp chung chung tự chế.
4. Cảnh chưa có `keywords`: bấm tìm thì để api trả lỗi của nó và hiển thị đúng
   thông điệp đó; nếu thẻ cảnh đã có sẵn ô sửa keywords thì gợi ý người dùng nhập
   ở đó. Không tự bịa keywords phía client.

## Yêu cầu chất lượng (không làm qua loa)

- Ảnh hiển thị trong lưới chỉ là thumbnail; ảnh lưu vào cảnh do server tải từ
  `url` gốc — không được lưu hay chèn `preview` ở bất kỳ đâu.
- Panel chọn ảnh phải xem rõ từng ảnh (thumbnail đủ lớn để phân biệt nội dung),
  không phải lưới icon bé không nhìn ra gì.
- Không thêm thư viện/npm package mới. Tái dùng component và style hiện có của
  trang sửa video.
- Sau khi chọn/tìm ảnh xong, trạng thái "cảnh thiếu ảnh" của video phải cập nhật
  đúng như khi upload tay (dùng cùng dữ liệu trả về như đường upload hiện tại).

## Kiểm chứng bắt buộc trước khi báo xong

- `cd web && npm run lint && npm run typecheck` — phải sạch.
- E2E: thêm hoặc cập nhật test cho luồng chọn ảnh bằng fake Pixabay (không gọi mạng
  thật), rồi chạy `npm run test:e2e`.
- Test tay trên local: tạo 1 video, sinh kịch bản, dùng "Chọn từ Pixabay" chọn ảnh
  cho 2 cảnh (trong đó có cảnh tiêu đề), dùng "Tìm ảnh" cho 1 cảnh, xác nhận cả 3
  cảnh có ảnh và nút Render hết bị chặn vì thiếu ảnh.

## Báo cáo

- Mở draft PR, mô tả theo mẫu 3 phần của `AGENTS.md` (Đã làm / Đã kiểm chứng — ghi
  rõ lệnh đã chạy và kết quả / Rủi ro còn lại).
- Cuối session, tóm tắt lại 3 phần đó trong chat. Không khai đã chạy kiểm chứng nào
  mà thực tế chưa chạy.
- Cập nhật `docs/architecture.md` nếu hành vi UI thay đổi so với mô tả hiện tại, và
  ghi chú tiến độ giai đoạn 1 vào mục backlog "Tạo ảnh bằng AI cho cảnh thiếu ảnh"
  trong `backlog.md` (ở thư mục gốc repo).
