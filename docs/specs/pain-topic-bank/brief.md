# Brief: Ngân hàng chủ đề từ nỗi đau và comment thật

> Trạng thái: brief để giao thi công (Claude Code hoặc Muse trực tiếp). Viết 2026-11-01.
> Mục backlog mới (2026-11-01). Là tầng đầu vào cho mục "Lịch chủ đề" đã có trong backlog — brief này KHÔNG làm lịch chủ đề.
> Đọc trước khi làm: `AGENTS.md`, `docs/decisions.md`, `docs/architecture.md`.

## Bối cảnh

Hiện tại pipeline bắt đầu khi đã có sẵn một chủ đề: thành viên nghĩ chủ đề trong đầu rồi tạo video. Không có bước nào đi tìm nhu cầu thật của khán giả 40+ trước. Trong khi nguồn chủ đề tốt nhất lại nằm sẵn ngoài kia: comment than phiền dưới các page dưỡng sinh lớn, câu hỏi lặp lại trong các nhóm Facebook về xương khớp / mất ngủ / tiểu đường, và cả comment trên chính Page của đội.

Brief này thêm một **Ngân hàng chủ đề** vào app: nơi gom các nỗi đau có thật (kèm chân dung người than và nguồn gốc), cho phép dán một đoạn comment thô vào để Claude trích xuất thành các mục nháp, thành viên duyệt rồi mới lưu; và từ một mục đã duyệt, tạo video ngay với chủ đề + nhóm kiến thức được điền sẵn.

## Nguyên tắc phạm vi (đọc kỹ — đây là phần dễ làm sai nhất)

- **KHÔNG tự động quét/cào Facebook.** Không bot đăng nhập, không crawl nhóm/page. Lý do: phải đăng nhập mới xem được, mong manh, và rủi ro tài khoản/Page. Đầu vào duy nhất là: (1) thành viên tự nhập tay, (2) thành viên tự copy–paste đoạn comment/bài viết vào ô trích xuất. Việc "đi gom" ở ngoài app vẫn là việc của con người; app chỉ xử lý phần đã gom về.
- Kết quả trích xuất của Claude là **bản nháp chờ duyệt**, không bao giờ tự lưu thẳng vào ngân hàng (theo đúng pattern duyệt của sản phẩm affiliate: AI/người nhập tạo draft, thành viên duyệt mới dùng được).
- Nỗi đau ghi bằng **nguyên văn ngôn ngữ của khán giả** ("đêm nào cũng chuột rút bắp chân"), không viết lại thành thuật ngữ y khoa — đó là chất liệu cho hook và tiêu đề sau này. Kỷ luật từ cấm của kho kiến thức áp dụng khi *viết kịch bản*, không áp dụng để kiểm duyệt mục trong ngân hàng (đây là dữ liệu thô nội bộ, không đăng đi đâu).

## Dữ liệu — bảng MỚI `topic_ideas`

- `id`, `created_at`, `created_by_id` như các bảng khác.
- `pain` (Text): câu nỗi đau bằng lời khán giả. Bắt buộc, không rỗng.
- `persona` (Text, mặc định ""): chân dung người than — tuổi, tình trạng, hoàn cảnh ("phụ nữ ~55, tiền tiểu đường, hay mất ngủ"). Không rõ thì để rỗng, không bịa.
- `knowledge_topic_id` (FK nullable → `knowledge_topics`): nhóm chủ đề gần nhất (xương khớp, giấc ngủ...). Để null khi chưa phân loại.
- `source_note` (Text, mặc định ""): nguồn gốc tự do — tên page/nhóm, link bài, hoặc "comment trên Page của đội". Chỉ để truy vết, không hiển thị ra ngoài.
- `source_text` (Text, mặc định ""): đoạn comment gốc đã dán vào (khi mục sinh ra từ trích xuất). Lưu để đối chiếu khi duyệt; mục nhập tay để rỗng.
- `score` (Integer, mặc định 0): độ "nóng" do thành viên chấm (số lần gặp lặp lại / mức độ đồng cảm). Chỉ là số sắp xếp nội bộ — KHÔNG hiển thị dạng điểm số ra giao diện công khai nào; trong app nội bộ hiển thị dạng nhãn "độ ưu tiên" 3 mức suy từ score (cao khi ≥ 5) hoặc cho sửa trực tiếp 0–10. (Ghi rõ: đây là công cụ nội bộ của đội, không phải UI cho khán giả.)
- `status` (String): `new | queued | used | dropped` — mới gom / đã xếp hàng làm / đã thành video / loại bỏ. Mặc định `new`.
- `video_id` (FK nullable → `videos`): video đã tạo từ mục này; set khi bấm "Tạo video", đồng thời `status` → `used`. Một mục chỉ gắn 1 video; muốn làm lại chủ đề đó thì tạo mục mới hoặc nhân bản video như thường.

## API

- `GET /api/topic-ideas?status=&knowledge_topic_id=` — danh sách, sắp xếp: `queued` trước, rồi score giảm dần, rồi mới nhất. Payload đủ các trường trên + tên nhóm chủ đề.
- `POST /api/topic-ideas` — tạo mục nhập tay (validate pain không rỗng; knowledge_topic_id phải tồn tại nếu có).
- `PATCH /api/topic-ideas/{id}` — sửa pain/persona/nhóm/score/status (kể cả dropped). Không sửa được `video_id` bằng tay.
- `DELETE /api/topic-ideas/{id}` — xoá hẳn (chỉ khi chưa gắn video; đã gắn video thì trả 409, muốn loại thì chuyển status `dropped`).
- `POST /api/topic-ideas/extract` — body `{text}` (đoạn comment/bài thô, giới hạn độ dài hợp lý — theo trần của các input LLM hiện có trong app; rỗng → 422). Đồng bộ MỘT lượt gọi LLM qua tầng `llm.py` (không qua jobs — jobs hiện gắn với video; đây là tiện ích một lượt, có timeout như các call LLM khác; lỗi LLM trả về câu lỗi quen thuộc của tầng llm). Trả về danh sách NHÁP (không lưu DB): mỗi nháp `{pain, persona, knowledge_topic_id}` — Claude chỉ được chọn `knowledge_topic_id` trong danh sách nhóm hiện có của app (truyền danh sách vào prompt; id lạ trong kết quả → coi như null). Prompt của extract là code đặt trong tầng llm/claude như OUTPUT_FORMAT, không phải knowledge prompt. Kết quả tối đa 10 nháp; đoạn text không có nỗi đau nào rõ ràng → mảng rỗng (không bịa).
- `POST /api/topic-ideas/{id}/create-video` — tạo một `Video` mới: `topic` = pain của mục (nguyên văn), `knowledge_topic_id` = của mục, `created_by_id` = người bấm; set `video_id` + `status = used` cho mục; trả payload video như endpoint tạo video hiện có để web chuyển thẳng sang trang video. Mục đã `used` → 409.

## Giao diện — trang MỚI "Ngân hàng chủ đề"

- Thêm mục điều hướng "Ngân hàng chủ đề" (đặt cạnh Kho kiến thức).
- Danh sách dạng thẻ/bảng như các trang quản trị khác: cột nỗi đau (nguyên văn), chân dung, nhóm chủ đề, nguồn, độ ưu tiên, trạng thái; lọc theo trạng thái và nhóm; nút đổi trạng thái nhanh (xếp hàng / loại bỏ).
- Form thêm tay: pain, persona, nhóm (select từ knowledge topics), nguồn, độ ưu tiên.
- Khung "Trích xuất từ comment": textarea dán text → bấm trích xuất → hiện danh sách nháp dạng checklist, mỗi nháp sửa được trước khi chọn → bấm "Lưu các mục đã chọn" thì gọi POST tạo từng mục (kèm `source_text` là đoạn gốc, `source_note` thành viên điền một lần cho cả mẻ). Nháp không chọn thì bỏ, không lưu vết.
- Nút "Tạo video" trên mỗi mục chưa dùng → tạo video và chuyển sang trang video đó.
- Trang này là công cụ nội bộ; vẫn tuân thủ hiển thị tốt trên điện thoại như các trang bảng khác đang hướng tới (dạng thẻ khi màn hình hẹp — nếu pattern thẻ chưa có sẵn thì giữ bảng cuộn như hiện trạng, không phát sinh thêm việc).

## Fake và test

- Fake LLM thêm kịch bản extract: với text chứa các câu mẫu cố định, trả 2–3 nháp hợp lệ (một nháp có knowledge_topic_id hợp lệ, một nháp null); với text không nỗi đau → mảng rỗng. Không gọi LLM thật trong test.
- Test tối thiểu:
  - CRUD: tạo tay (pain rỗng → 422), sửa, lọc theo status/nhóm, thứ tự sắp xếp (queued trước, score giảm dần).
  - Xoá mục đã gắn video → 409; mục chưa gắn → xoá được.
  - Extract: trả nháp đúng khuôn, id nhóm lạ bị ép về null, text rỗng → 422, extract KHÔNG tạo hàng nào trong DB (chỉ trả nháp).
  - Tạo video từ mục: video có topic = pain nguyên văn + đúng knowledge_topic_id; mục chuyển `used` và gắn video_id; gọi lần hai → 409.
- E2E: dán đoạn comment mẫu → trích xuất → chọn 1 nháp → lưu → bấm Tạo video → tới được trang video với chủ đề đã điền.

## Không làm trong brief này

- Không crawl/quét Facebook tự động dưới mọi hình thức (xem Nguyên tắc phạm vi).
- Không chấm điểm tự động bằng AI cho score — AI chỉ trích xuất; độ ưu tiên do thành viên quyết.
- Không làm lịch chủ đề / ma trận mùa ở đây (mục backlog riêng). Ngân hàng này chỉ là nguồn đầu vào cho nó sau này.
- Không sinh kịch bản hàng loạt từ ngân hàng; mỗi video vẫn tạo và duyệt riêng như hiện tại.
- Không thống kê nâng cao (tỉ lệ mục → video thắng thuộc brief performance-loop, làm sau khi có số liệu).

## Tài liệu phải cập nhật khi thi công

- `docs/architecture.md`: bảng `topic_ideas`, các endpoint, trang Ngân hàng chủ đề, endpoint extract đồng bộ qua tầng llm.
- `docs/decisions.md`: thêm mục mới — ngân hàng chủ đề là dữ liệu thô nội bộ (không áp từ cấm), đầu vào chỉ nhập tay/dán (không crawl Facebook), trích xuất AI luôn qua duyệt của thành viên.
- `backlog.md`: khi làm xong, XÓA mục ngân hàng chủ đề (theo quy ước của file); mục "Lịch chủ đề" giữ nguyên.

## Kiểm chứng khi thi công xong

- `cd api && .venv/bin/python -m pytest -q` và `.venv/bin/ruff check src tests scripts`
- `cd web && npm run lint && npm run typecheck` + E2E liên quan.
- Test tay local: dán thử một đoạn comment thật (tự lấy từ Page) → xem nháp trích xuất có đúng nguyên văn nỗi đau và không bịa chân dung không.
