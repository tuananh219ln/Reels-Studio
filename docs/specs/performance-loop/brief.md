# Brief: Vòng đo chỉ số 48 giờ + nhân bản video thắng theo angle

> Trạng thái: brief để giao thi công (Claude Code hoặc Muse trực tiếp). Viết 2026-11-01.
> Bao phủ 2 mục backlog (2026-10-28): "Đo chỉ số sau 48 giờ" và "Nhân bản video thắng".
> Đọc trước khi làm: `AGENTS.md`, `docs/decisions.md`, `docs/architecture.md`.

## Bối cảnh

App đã đăng được reel lên Facebook Page (bảng `publications` lưu `remote_id` là id reel phía Facebook, `published_at`, `fanpage_id`; token Page lấy qua `fanpages`). Nhưng sau khi đăng, không ai biết video nào thắng: không có số view/share nào chảy về app, KPI của kênh (share/view ≥ 0,2%; video vượt 10× view trung vị thì làm 3 biến thể) hiện phải kiểm tra tay trên Page.

Brief này khép vòng lặp đó trong app:

1. Tự động đo chỉ số của mỗi reel sau 48 giờ kể từ lúc đăng (và đo lại được khi cần).
2. Tính trung vị + cờ "video thắng" + KPI tuần ngay trong app.
3. Từ một video thắng, Claude đề xuất 10 biến thể xếp hạng — mỗi biến thể chỉ đổi ĐÚNG MỘT yếu tố của angle (thực phẩm / mốc tuổi / nhóm bệnh) — thành viên chọn tối đa 3 để tạo bản nháp nhân bản qua cơ chế "Nhân bản" sẵn có.

## Hiện trạng liên quan (đã có, dùng lại — không xây mới)

- `publications`: 1 hàng cho mỗi (video, platform); `remote_id` có trước cả khi upload xong; trạng thái `pending | scheduled | published`; `published_at` là mốc tính 48 giờ. Với bài lên lịch, `published_at` chỉ biết khi job publish xác nhận reel đã live — lấy mốc đó, không lấy `scheduled_at`.
- `facebook.py`: đã có `_read(page, path, **fields)` cho GET Graph API và bộ phân loại lỗi (`TOKEN_ERRORS`, `PERMISSION_ERRORS`, `RATE_LIMIT_ERRORS`, HTTP 429/5xx) với câu chữ tiếng Việt. Đo chỉ số đi qua đây, không viết HTTP riêng.
- `jobs`: hàng đợi là bảng `jobs`, worker nhận job `queued` ngay khi thấy. Job gắn với một video; index unique một phần đảm bảo 1 job active/video. Chưa có khái niệm "chạy sau thời điểm X" — brief này thêm (mục 1).
- Fake services (`api/scripts/fake_services.py`) đã giả lập Facebook cho publish; mở rộng fake là cách test duy nhất được phép (không gọi Graph API thật trong test).
- "Nhân bản" hiện tại: nút bấm tạo 1 biến thể theo yêu cầu đổi tự do, snapshot lưu ở `videos.clone_source`. Cơ chế tạo nháp từ một biến thể đề xuất phải đi qua đúng đường này.

## Mục 1 — Job "metrics" chạy ở mốc 48 giờ

- Thêm cột `jobs.run_after` (DateTime tz, nullable; migration mới): worker chỉ nhận job `queued` khi `run_after IS NULL OR run_after <= now`. Job thường để null → hành vi cũ không đổi.
- Thêm kind job mới `"metrics"` (cập nhật comment liệt kê kind trong `models.py`, `JOB_KINDS` trong `videos.py` với nhãn "Đo chỉ số", và mọi Record exhaustiveness phía web như đã làm với kind "image").
- Khi job publish kết thúc với publication ở trạng thái `published` và đã có `published_at`: tự enqueue 1 job metrics cho video đó với `run_after = published_at + 48 giờ`. Enqueue phải idempotent theo publication: nếu publication đó đã có job metrics đang chờ/đang chạy hoặc đã có snapshot 48 giờ thì không tạo thêm (chống publish retry tạo trùng).
- Job metrics chạy:
  - Lấy publication facebook của video; nếu chưa `published` hoặc chưa có `remote_id` → job failed với câu rõ ràng (không gọi Facebook).
  - Gọi `facebook.reel_insights(page, remote_id)` (hàm mới trong `facebook.py`, dùng `_read`): trả dict chuẩn hoá `{views, shares, comments, reactions, saves}` — mỗi giá trị là int hoặc None khi Facebook không cung cấp chỉ số đó cho reel. Việc ánh xạ từ response Graph API vào dict này gói gọn trong đúng hàm này, để nếu tên metric phía Meta khác với giả định thì chỉ sửa một chỗ. Token/lỗi quyền/giới hạn lượt dùng lại phân loại lỗi sẵn có của `facebook.py` (job failed với đúng câu chữ đó).
  - Lưu kết quả vào bảng MỚI `publication_metrics`: `publication_id` (unique), `views`, `shares`, `comments`, `reactions`, `saves` (các cột số đều nullable), `measured_at`, `window` (chuỗi: `"48h"` cho lượt tự động, `"manual"` cho lượt đo lại tay). Đo lại thì GHI ĐÈ cùng một hàng (cập nhật số + `measured_at` + `window`), không thêm hàng mới.
- Nút "Đo lại chỉ số" ở trang video (chỉ hiện khi video đã published): enqueue job metrics ngay (`run_after = null`), vẫn tôn trọng khóa 1-job-active/video như mọi job khác.

## Mục 2 — KPI, trung vị và cờ "video thắng"

- Tính ở tầng API (không lưu thêm cột): trên tập các publication facebook đã có snapshot `publication_metrics`:
  - `median_views`: trung vị của `views` (bỏ qua snapshot có views = None).
  - Video là "thắng" khi có snapshot, `views >= 10 × median_views`, và tập mẫu có **ít nhất 5** snapshot có views. Dưới 5 mẫu: không gắn cờ cho ai cả, UI ghi "chưa đủ dữ liệu để so trung vị".
  - `share_rate = shares / views` cho từng video (None khi thiếu số).
- Payload video (chi tiết + danh sách) thêm khối `metrics` (null khi chưa đo): `{views, shares, comments, reactions, saves, measured_at, window, share_rate, is_winner, median_views}`.
- Trang video hiển thị khối chỉ số (số đo, thời điểm đo, so với trung vị dạng "gấp ×N trung vị" khi có) + badge "Video thắng" khi `is_winner`.
- Trang Bài đăng (danh sách publications) thêm cột view/share và tỉ lệ share/view cho các bài đã đo; một dải KPI tuần ở đầu trang: số video đã đo trong 7 ngày, view trung vị, số video thắng, tỉ lệ video có share_rate ≥ 0,2%. Tính KPI tuần từ cùng dữ liệu snapshot, không thêm bảng.

## Mục 3 — Đề xuất biến thể theo angle (job "variants")

- Chỉ dành cho video thắng (nút "Đề xuất biến thể" ở trang video, chỉ hiện khi `is_winner`): enqueue kind job MỚI `"variants"` (nhãn "Đề xuất biến thể").
- Đầu vào cho Claude (qua tầng `llm.py` như job script/clone, đếm `claude_calls` như thường): kịch bản đầy đủ của video gốc (tiêu đề + các cảnh), khối metrics của nó, và trung vị hiện tại. Prompt của job này là code (như `OUTPUT_FORMAT` của script), đặt cạnh prompt clone trong tầng llm/claude hiện có — không đưa vào knowledge prompt của thành viên.
- Đầu ra bắt buộc (JSON, validate như parse của script job): đúng 10 biến thể, mỗi biến thể gồm:
  - `change_type`: một trong `"food" | "age" | "group"` (đổi thực phẩm / đổi mốc tuổi / đổi nhóm bệnh) — mỗi biến thể CHỈ đổi một loại này, giữ nguyên các yếu tố còn lại của angle (hook, cấu trúc list, nỗi đau).
  - `title`: tiêu đề dự kiến cho biến thể.
  - `change_request`: câu yêu cầu đổi cụ thể, dùng được nguyên văn làm đầu vào cho job clone hiện tại.
  - `reason`: 1 câu vì sao biến thể này có khả năng viral (dựa trên yếu tố nào của video gốc).
  - Thứ tự trong mảng là thứ tự xếp hạng (đầu = khả năng cao nhất) — không thêm trường điểm số.
- Lưu kết quả vào cột MỚI `videos.variant_suggestions` (JSONB, default rỗng). Chạy lại job thì thay thế danh sách cũ.
- UI: danh sách 10 biến thể ở trang video (hiển thị change_type bằng nhãn tiếng Việt, title, reason), mỗi biến thể có nút "Tạo bản nháp" → tạo video nháp nhân bản bằng ĐÚNG cơ chế clone hiện tại với `change_request` của biến thể đó (snapshot `clone_source` như clone thường, cộng thêm đánh dấu biến thể xuất phát từ video thắng nào — ghi vào chính dict `clone_source`, không thêm cột). Không tự động tạo cả 3: thành viên bấm từng cái (kỷ luật của backlog là "làm ngay 3" trong số 10 — app hỗ trợ tạo tối đa 3 bản nháp từ một danh sách đề xuất; biến thể đã tạo nháp thì đánh dấu đã dùng trong UI dựa trên `clone_source` của các video con, không lưu trạng thái riêng).
- Video không thắng thì không gọi được job variants (endpoint trả 409 với câu "Chỉ video thắng mới đề xuất biến thể").

## Fake và test

- Fake Facebook thêm endpoint insights: với mỗi remote_id, test đặt được bộ số `{views, shares, comments, reactions, saves}` (state theo remote_id); mặc định trả bộ số cố định. Token sai → lỗi như các endpoint fake khác.
- Fake LLM thêm kịch bản cho job variants: trả 10 biến thể hợp lệ cố định (đủ 3 change_type).
- Test tối thiểu:
  - Worker không nhận job metrics khi `run_after` còn ở tương lai; nhận khi đã tới hạn (kiểm ở tầng truy vấn nhận job, không ngủ thật).
  - Publish xong tự có job metrics với `run_after = published_at + 48h`; publish retry không tạo job thứ hai.
  - Job metrics lưu đúng snapshot; đo lại ghi đè cùng hàng và đổi `window` thành `"manual"`.
  - Facebook báo lỗi token → job failed với câu token của `facebook.py`; publication chưa published → failed không gọi Facebook (fake ghi 0 lượt gọi insights).
  - KPI: dựng 5+ snapshot với số biết trước → median đúng, đúng video được cờ thắng, share_rate đúng; 4 snapshot → không ai có cờ.
  - Job variants: video thắng → 10 biến thể lưu đúng thứ tự, mỗi biến thể đúng 1 change_type hợp lệ; video không thắng → endpoint 409; tạo nháp từ biến thể đi qua đường clone và mang `clone_source` có đánh dấu nguồn.
- E2E: một luồng đăng bài bằng fake → (điều khiển thời gian qua dữ liệu seed, không chờ thật) đo chỉ số → thấy khối metrics + badge trên trang video.

## Không làm trong brief này

- Không đo chỉ số TikTok/Instagram (chưa đăng tự động lên đó).
- Không tự động nhân bản/tự đăng biến thể: mọi bản nháp đều do thành viên bấm tạo và duyệt như video thường.
- Không biểu đồ chuỗi thời gian, không đo nhiều mốc (chỉ 48h + đo lại tay ghi đè).
- Không dùng số liệu này để tự thay đổi prompt kho kiến thức.

## Tài liệu phải cập nhật khi thi công

- `docs/architecture.md`: job kinds mới (metrics, variants), cột `jobs.run_after`, bảng `publication_metrics`, cột `videos.variant_suggestions`, luồng publish → metrics.
- `docs/deployment.md`: không biến env mới (dùng token Page sẵn có) — nếu phát sinh thì theo quy ước thêm hàng cùng PR.
- `docs/decisions.md`: thêm mục mới — đo chỉ số qua Graph API insights của chính reel đã đăng, snapshot 48h ghi đè khi đo lại, cờ thắng cần tối thiểu 5 mẫu, biến thể mỗi cái chỉ đổi một yếu tố angle.
- `backlog.md`: khi làm xong, XÓA 2 mục "Đo chỉ số sau 48 giờ" và "Nhân bản video thắng" (theo quy ước của file).

## Kiểm chứng khi thi công xong

- `cd api && .venv/bin/python -m pytest -q` và `.venv/bin/ruff check src tests scripts`
- `cd web && npm run lint && npm run typecheck` + E2E liên quan.
- Test tay local với fake Facebook: đăng 1 video, ép `run_after` về quá khứ trong DB local để job metrics chạy ngay, kiểm tra snapshot + badge.
- Rủi ro còn lại phải ghi trong báo cáo: tên metric insights thật của Meta cho reel chưa được gọi thử bằng token thật — `facebook.reel_insights` là chỗ duy nhất cần chỉnh nếu số liệu thật khác giả định.
