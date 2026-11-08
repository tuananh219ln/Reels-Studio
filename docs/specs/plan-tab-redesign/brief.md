# Brief — Làm lại tab Kế hoạch 30 ngày: nới số ý/ngày, nút Sửa rõ ràng, bố cục lịch tháng

> Soạn 08/11/2026 theo yêu cầu của user (chủ sản phẩm): (1) tab kế hoạch
> phải có NÚT CHỈNH SỬA rõ ràng; (2) số ý tưởng mỗi ngày phải chỉnh được
> xuống 2 hoặc số khác; (3) bố cục mới theo bản phác họa + bản HTML bấm
> thử mà user đã xem và duyệt hướng trong chat ngày 08/11.
> Cách làm theo lệ của team: đọc AGENTS.md + docs/decisions.md trước;
> nhánh riêng cho từng PR; TDD (viết test trước); chạy đủ test api + web;
> báo cáo 3 phần theo AGENTS.md; không tự merge.

## Bối cảnh (đã kiểm chứng trong code ngày 08/11)

1. **Số ý/ngày bị găm cứng 3–5 ở cả hai tầng.**
   - `api/src/reels_api/plans.py`: `MIN_PER_DAY = 3`, `MAX_PER_DAY = 5`.
     Mọi chỗ khác đều suy từ hai hằng số này: `routes_plans.py` PATCH
     `/plans/{topic_id}` kiểm `per_day` ngoài khoảng thì 422 (thông điệp
     lỗi tự lấy theo hằng số); `_room()` chặn ngày đủ `MAX_PER_DAY` ý
     (409 `plan_day_full`); `check_plan`: ngày quá `MAX_PER_DAY` ý là lỗi
     chặn lưu, ngày dưới `MIN_PER_DAY` chỉ là cảnh báo;
     `MAX_IDEAS = PLAN_DAYS * MAX_PER_DAY`; `MAX_POST_TIMES = MAX_PER_DAY`
     và `check_post_times` cho 1..`MAX_POST_TIMES` giờ đăng.
   - `web/src/components/plan/PlanTab.tsx` khai lại `MIN_PER_DAY = 3`,
     `MAX_PER_DAY = 5` ở đầu file: ô `InputNumber` "Số ý tưởng mỗi ngày"
     lấy min/max từ đó; nút "+" của DayCard bị khoá khi đủ `MAX_PER_DAY`;
     DayPicker khoá ngày đủ và in nhãn "(x/MAX)"; DayCard in cảnh báo
     "Mới có x ý tưởng, nên có MIN–MAX".
   - Giả định cũ "mỗi nhóm đăng 3–5 video/ngày" không còn đúng: các page
     thật của team đăng 1–2 video/ngày, nên chủ sản phẩm không đặt được 2.
2. **Sửa ý tưởng hiện không có nút Sửa.** Trong `IdeaCard` (PlanTab.tsx),
   từng trường (topic, pain_group, pain, hook) dùng `Typography editable`
   — biểu tượng bút chì chỉ hiện khi rê chuột, mỗi trường tự PATCH riêng
   khi Enter/rời ô. Người dùng không nhận ra là sửa được, và không có
   form sửa một lần với Lưu/Huỷ. Đây là phàn nàn số 1 của chủ sản phẩm.
3. **Bố cục hiện tại.** PlanView gồm: thẻ thiết lập phẳng (ngày bắt đầu,
   số ý/ngày, giờ đăng — mọi ô đều tự lưu ngay khi đổi — kèm TodayLine
   một dòng chữ), ProgressStrip (30 ô vuông nhỏ + chú thích, bấm để neo
   tới thẻ ngày), VerdictTarget, nút Nhập file / Tạo bằng AI, một đoạn
   văn hướng dẫn dài, PlanPromptCard (Collapse), hàng lọc (trạng thái /
   nhóm nỗi đau / tìm kiếm / Đầy đủ–Gọn — đợt brief trước, GIỮ NGUYÊN),
   rồi 30 DayCard xếp lưới. Backlog là tab riêng + panel bên khi mở.
4. **Payload đã đủ, KHÔNG cần sửa API cho phần bố cục.** `plan_payload`
   đã trả: `start_date`, `today_day`, `per_day`, `post_times`,
   `video_target`, `video_count`, `made`, `share_goal`, và `items[]` có
   `status` (đủ 6 trạng thái: idea, started, scripted, done, scheduled,
   posted), `status_label`, `video_id`, `post_at`, `suggested_post_at`,
   `posts[]` (số 48h + so trung vị). Các endpoint ý tưởng cũng đã đủ:
   POST `/plans/{topic_id}/items`, PATCH + DELETE `/plans/items/{id}`
   (PATCH gồm cả đổi ngày/vị trí). Kéo–thả đổi ngày và thả vào tab
   Backlog đang chạy bằng chính PATCH này.

## Phần 1 — Nới khoảng số ý tưởng mỗi ngày thành 1–10 (backend + web)

- Đổi `MIN_PER_DAY = 1`, `MAX_PER_DAY = 10` trong `plans.py` và trong
  `PlanTab.tsx`. Mọi hành vi suy theo hằng số (PATCH per_day, `_room`,
  `check_plan`, DayPicker, cảnh báo DayCard…) tự đi theo — kiểm tra lại
  từng chỗ, không sửa tay lẻ tẻ.
- Cập nhật các ghi chú đã cũ theo số mới: comment "1 to 5" ở
  `PlanPatchBody.post_times` (routes_plans.py), docstring "the 5-a-day
  limit" ở `_topic`, và câu chữ nào trong code nhắc "3–5" / "3-5".
- Hệ quả phải ý thức, KHÔNG tách riêng: `MAX_IDEAS` thành 300 (bằng
  `MAX_BACKLOG`, chấp nhận được); `MAX_POST_TIMES` thành 10 (giờ đăng
  tối đa 10 — chấp nhận được, đừng gỡ liên kết này).
- Tạo kế hoạch bằng AI với per_day nhỏ phải chạy đúng: `build_prompt`
  đã nói "mỗi ngày đúng {per_day} ý tưởng", `parse_output` cắt theo
  `MAX_PER_DAY` — viết test với per_day = 2 qua fake service.
- Test (viết trước, phải đỏ trước khi sửa): PATCH per_day = 1, 2, 10
  được chấp nhận; 0 và 11 bị 422; thêm ý thứ 10 vào một ngày được, ý
  thứ 11 bị 409; một ngày có 2 ý không sinh cảnh báo "dưới mức tối
  thiểu"; kế hoạch cũ đang để 4 ý/ngày không bị ảnh hưởng.
- Web: ô InputNumber cho chọn 1–10; test web hiện có cho PlanTab phải
  qua, bổ sung ca đặt per_day = 2 nếu harness cho phép.

## Phần 2 — Nút "Sửa" rõ ràng trên mỗi thẻ ý tưởng

- Thêm nút **"Sửa"** (icon EditOutlined + chữ "Sửa") luôn nhìn thấy
  trên mỗi IdeaCard, ở cả chế độ Đầy đủ và Gọn (cạnh nút Tạo video /
  Mở video hiện có), không cần rê chuột hay mở rộng thẻ mới thấy.
- Bấm "Sửa" mở MỘT form sửa (Modal hoặc FormDrawer — theo mẫu form
  AddIdeaModal đang có trong cùng file) gồm đủ 4 trường: Chủ đề, Nhóm
  nỗi đau, Nỗi đau, Góc hook; nút **Lưu** / **Huỷ** rõ ràng. Lưu = một
  PATCH `/plans/items/{id}` duy nhất cho cả 4 trường; lỗi validation
  của API hiện trong form, không đóng form.
- Thay cơ chế `Typography editable` từng trường bằng form này (một
  đường sửa duy nhất, tránh hai cơ chế lệch nhau và tránh sửa lỡ tay
  khi bấm vào chữ). Cập nhật các test web đang dựa vào editable.
- Các nút hiện có giữ nguyên: Tạo video / Mở video, chuyển về Backlog,
  Xoá (Popconfirm), DayPicker "Xếp vào ngày…", kéo–thả.

## Phần 3 — Bố cục lịch tháng + dải "Hôm nay" + gom Thiết lập (thuần web)

Thay lưới 30 DayCard bằng bố cục đã duyệt trong bản bấm thử:

1. **Lịch theo tuần.** 5 khối tuần (ngày 1–7, 8–14, 15–21, 22–28,
   29–30). Mỗi khối có dòng đầu: "Tuần N · dd/mm – dd/mm" (ngày dương
   lịch suy từ `start_date`; chưa có start_date thì chỉ ghi số ngày) +
   tóm tắt tuần (đã làm mấy, đã lên lịch mấy — đếm từ items). Thân khối
   là lưới 7 cột ô ngày; ô ngày gồm: thứ + dd/mm (hoặc "Ngày N" khi
   chưa có start_date), dấu "Hôm nay" khi `today_day` trùng, và các
   chip ý tưởng (tiêu đề rút gọn, màu theo `PLAN_STATUS_COLORS` /
   `statusColor` hiện có). Ô trống hiện viền đứt nét "+ Thêm ý". Ô của
   ngày đang chọn có viền nổi bật; mặc định chọn `today_day` (nằm trong
   1–30), không thì ngày 1. Màn hình hẹp: lưới co còn 2–3 cột, không
   tràn ngang.
2. **Panel chi tiết ngày** ngay dưới lịch: hiện IdeaCard đầy đủ của
   ngày đang chọn (đúng component hiện có, gồm PostNumbers, giờ gợi ý,
   DayPicker, nút Sửa của Phần 2) + nút thêm ý cho ngày đó. Hàng lọc và
   chế độ Đầy đủ/Gọn áp lên panel chi tiết như hiện nay; chip trên lịch
   không bị lọc.
3. **Dải "Hôm nay"** thay TodayLine: một dải riêng trên cùng liệt kê ý
   tưởng của hôm nay (tiêu đề + Tag trạng thái + nút hành động kế tiếp
   Tạo video / Mở video + nút Sửa). Chưa có start_date: dải hiện câu
   nhắc chọn ngày bắt đầu (đúng nội dung TodayLine hiện tại); chưa tới
   ngày 1 / đã qua ngày 30: hiện câu tương ứng như TodayLine.
4. **Hàng tóm tắt** trên cùng: "Đã làm {made}/{tổng ý có ngày} · Đã lên
   lịch {số scheduled} · Ngày còn trống {số ngày 0 ý}" và khối
   VerdictTarget hiện có giữ nguyên hành vi, đưa vào cùng khu vực đầu
   tab.
5. **Gom Thiết lập.** Một nút "Thiết lập" mở/đóng một panel chứa: Ngày
   bắt đầu (DatePicker), Số ý tưởng mỗi ngày (InputNumber 1–10 theo
   Phần 1), Giờ đăng (Select tags như PostTimes hiện có), Mục tiêu
   video cho verdict. KHÁC hành vi hiện tại (mọi ô đang tự lưu ngay):
   panel sửa tại chỗ rồi bấm **Lưu** mới PATCH một lần các trường đã
   đổi (PATCH plan nhận từng phần), **Huỷ** thì bỏ thay đổi. Đây là
   thay đổi có chủ ý theo bản duyệt — phải có test phủ: sửa mà bấm Huỷ
   thì kế hoạch không đổi; bấm Lưu thì đổi đúng các trường đã sửa.
   PlanPromptCard giữ nguyên vị trí và hành vi.
6. **Bỏ ProgressStrip** (lịch đã thay vai trò của nó, kể cả việc nhảy
   tới ngày: bấm ô ngày thay cho neo link), nhưng GIỮ hàng chú thích
   màu trạng thái — chuyển lên đầu khu vực lịch.
7. **Kéo–thả giữ nguyên:** ô ngày trên lịch là vùng thả (thả ý tưởng
   vào = chuyển tới ngày đó, đúng luồng PATCH + cảnh báo "bài đã hẹn
   giờ không đổi giờ đăng" hiện có); thả lên tên tab Backlog vẫn chạy;
   ngày đã đủ `MAX_PER_DAY` ý thì từ chối thả như DayPicker đang khoá.
8. Đoạn văn hướng dẫn dài hiện tại rút còn một dòng gợi ý ngắn; các
   Alert việc tạo AI lỗi / bản nháp AI và nút Nhập file / Tạo bằng AI
   giữ nguyên vị trí và hành vi.

## Ngoài phạm vi

- Không đổi payload hay endpoint của plans (đã đủ — xem Bối cảnh 4),
  trừ hệ quả của Phần 1.
- Không làm "AI tạo ý cho riêng một ngày" (chưa có endpoint; nút thêm
  ý của ô trống/panel chỉ mở form thêm tay và chọn từ Backlog như hiện
  có).
- Không đụng luồng nhập file / xem trước / lưu bản nháp AI, Backlog,
  prompt kế hoạch, và cơ chế đo 48h.

## Thứ tự và nghiệm thu

- PR 1: Phần 1 + Phần 2 (nhỏ, giá trị ngay: đặt được 2 ý/ngày và có
  nút Sửa). PR 2: Phần 3. Mỗi PR một nhánh riêng, ghi quyết định vào
  docs/decisions.md, báo cáo 3 phần, không tự merge.
- Nghiệm thu PR 1: đặt per_day = 2 lưu được ở cả UI và API; tạo tay ý
  thứ 2 trong ngày được; nút "Sửa" hiện trên mọi thẻ, sửa 4 trường lưu
  một lần, Huỷ không đổi gì; test api (test_plans.py + toàn bộ pytest)
  và test/lint/typecheck web đều xanh.
- Nghiệm thu PR 2: với start_date = 02/11/2026, ô ngày 7 hiện "CN
  08/11" và dấu Hôm nay khi today_day = 7; bấm ô ngày đổi panel chi
  tiết đúng ngày đó; tóm tắt tuần đếm đúng; kéo ý tưởng thả vào ô ngày
  khác thì ý chuyển ngày; panel Thiết lập: sửa rồi Huỷ không đổi, sửa
  rồi Lưu đổi đúng; lọc + Gọn vẫn áp đúng lên panel chi tiết; Backlog
  không thay đổi hành vi.