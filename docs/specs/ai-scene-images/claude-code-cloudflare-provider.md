# Bàn giao Claude Code: THÊM Cloudflare Workers AI làm provider tạo ảnh thứ hai (giữ nguyên Gemini)

> Phiên Claude Code: model **Sonnet 5.5**, effort **medium**. TUYỆT ĐỐI không dùng subagent. Không commit, không merge — chủ repo tự lo. Dán toàn bộ phần dưới đường kẻ vào Claude Code.

---

# Việc: thêm Cloudflare Workers AI làm provider thứ hai cho tính năng "Tạo ảnh AI cho cảnh thiếu" — KHÔNG thay thế Gemini

## Bối cảnh và quyết định đã chốt

- Tính năng tạo ảnh AI (job kind "image") hiện chạy với Gemini: module `api/src/reels_api/imagegen.py`, fake Gemini trong `api/scripts/fake_services.py`, test `api/tests/test_image_jobs.py`. Key được resolve qua `source_keys` (trang Cài đặt › Nguồn tư liệu, tên nguồn "gemini") rồi truyền vào `generate_image(prompt, key)`; `image_source` của cảnh lưu dạng `ai:<model>`.
- Chủ repo quyết định: **GIỮ NGUYÊN Gemini** (để dùng khi có gói trả phí) và **THÊM Cloudflare Workers AI** làm provider thứ hai. Lý do thêm: free tier Gemini thực tế không cho tạo ảnh (quota ảnh gần như bằng 0), còn Cloudflare Workers AI có hạn mức free 10.000 neurons/ngày (reset hằng ngày, cả gói Workers Free); model FLUX.1 schnell tốn ~173 neurons/ảnh → khoảng 57 ảnh/ngày, thừa cho nhu cầu 1–3 video/ngày. Chủ repo đã có sẵn tài khoản Cloudflare.
- Provider đang dùng được chọn bằng biến env `IMAGE_GEN_PROVIDER` (`gemini` | `cloudflare`), **mặc định `gemini`** — hệ thống hiện tại không đổi hành vi nếu không đặt biến này.
- Đọc trước: `AGENTS.md` và `docs/decisions.md`. Mục chốt Gemini 2026-10-31 VẪN hiệu lực; đợt này ghi thêm mục mới, KHÔNG sửa mục cũ.

## Hợp đồng Cloudflare Workers AI (đã kiểm chứng từ tài liệu chính thức — theo đúng đây, không cần tra lại)

- Endpoint: `POST {IMAGE_GEN_CF_API_URL}/accounts/{IMAGE_GEN_CF_ACCOUNT_ID}/ai/run/{IMAGE_GEN_CF_MODEL}`
  - `IMAGE_GEN_CF_API_URL` mặc định: `https://api.cloudflare.com/client/v4`
  - `IMAGE_GEN_CF_MODEL` mặc định: `@cf/black-forest-labs/flux-1-schnell`
  - `IMAGE_GEN_CF_ACCOUNT_ID`: Account ID của tài khoản Cloudflare (không phải bí mật).
  - Key (API token) đi qua `source_keys` với tên nguồn MỚI `"cloudflare"`, biến env `IMAGE_GEN_CF_API_KEY` — song song và độc lập với key Gemini.
- Header: `Authorization: Bearer <key>`, `Content-Type: application/json`.
- Body JSON chỉ gồm: `{"prompt": <prompt>, "steps": 4}`. QUAN TRỌNG: trên Cloudflare, FLUX.1 schnell BỎ QUA width/height — ảnh trả về luôn vuông 1024×1024. Không gửi width/height.
- Thành công: HTTP 200, JSON `{"result": {"image": "<base64 JPEG>"}, "success": true, "errors": [], "messages": []}`.
- Lỗi: HTTP 4xx/5xx hoặc `"success": false`, kèm `"errors": [{"code": ..., "message": "..."}]`.

## Khung dọc 9:16 cho nhánh Cloudflare (xử lý phía client)

- Provider này trả ảnh vuông nên nhánh Cloudflare trong `imagegen` phải tự cắt giữa (center-crop) về đúng tỉ lệ 9:16 rồi mã hoá lại JPEG (quality 90) trước khi trả bytes. Pillow đã là dependency sẵn của `reels_api` (`uploads.py` đang dùng) — dùng luôn, không thêm dependency mới.
- Ảnh đã đúng 9:16 sẵn (trong sai số nhỏ) thì giữ nguyên bytes gốc.
- Nhánh Gemini KHÔNG cắt gì cả (Gemini đã trả đúng 9:16 theo cấu hình sẵn).

## Cấu trúc code cần đạt

1. `api/src/reels_api/config.py` — THÊM (không sửa các hàm Gemini hiện có):
   - `image_gen_provider()`: đọc `IMAGE_GEN_PROVIDER`; trả `"cloudflare"` khi giá trị (thường hoá chữ thường, bỏ khoảng trắng) đúng bằng `"cloudflare"`, mọi trường hợp còn lại trả `"gemini"`.
   - `image_gen_cf_api_url()`: đọc `IMAGE_GEN_CF_API_URL`, mặc định `https://api.cloudflare.com/client/v4` (bỏ dấu `/` cuối như các hàm *_api_url khác).
   - `image_gen_cf_account_id()`: đọc `IMAGE_GEN_CF_ACCOUNT_ID`.
   - `image_gen_cf_model()`: đọc `IMAGE_GEN_CF_MODEL`, mặc định `@cf/black-forest-labs/flux-1-schnell`.
2. `api/src/reels_api/imagegen.py` — mở rộng, KHÔNG viết lại nhánh Gemini:
   - `generate_image(prompt, key, provider)`: dispatch theo `provider` — `"cloudflare"` → hàm mới `_generate_cloudflare(prompt, key)`; còn lại → code Gemini hiện tại NGUYÊN VẸN (url, header x-goog-api-key, generationConfig 9:16, promptFeedback, câu chữ lỗi — không đổi một chữ).
   - `_generate_cloudflare` theo hợp đồng ở trên; dùng chung class `ImageGenError` và `REQUEST_TIMEOUT`; sau khi decode base64 thì cắt 9:16 bằng Pillow như mục trên rồi mới trả bytes.
   - Phân loại lỗi của nhánh Cloudflare:
     - Thiếu key → fatal: "Chưa có API token Cloudflare nên không tạo được ảnh AI: nhập token ở Cài đặt › Nguồn tư liệu"
     - Thiếu IMAGE_GEN_CF_ACCOUNT_ID → fatal: "Chưa cấu hình IMAGE_GEN_CF_ACCOUNT_ID (Account ID của Cloudflare) trong .env của server"
     - HTTP 401/403 → fatal: "API token Cloudflare không hợp lệ: kiểm tra lại ở Cài đặt › Nguồn tư liệu"
     - HTTP 429, hoặc thông điệp lỗi của provider chứa "neuron"/"quota"/"limit" → fatal: "Tài khoản Cloudflare đã hết hạn mức neurons hôm nay, đợi qua ngày mới (reset 00:00 UTC) hoặc nâng gói"
     - success=false / 4xx khác → lỗi từng cảnh: "Cloudflare từ chối tạo ảnh cho cảnh này" (detail chứa nguyên văn message của provider)
     - HTTP ≥500 → lỗi từng cảnh: "Cloudflare đang lỗi (HTTP {status}), thử lại sau"
     - Lỗi mạng/timeout → lỗi từng cảnh: "Không kết nối được Cloudflare, kiểm tra mạng rồi thử lại"
     - Base64 hỏng hoặc Pillow không đọc được ảnh → lỗi từng cảnh: "Cloudflare trả ảnh không đọc được, thử lại sau"
     - HTTP 200 nhưng không có result.image → lỗi từng cảnh: "Cloudflare không trả ảnh cho cảnh này, thử lại sau"
   - Cập nhật docstring đầu file: module nay phục vụ hai provider, dispatch theo provider; nhánh Cloudflare cắt 9:16 tại đây.
3. `api/src/reels_api/source_keys.py` — `ENV_NAMES` THÊM `"cloudflare": "IMAGE_GEN_CF_API_KEY"` (giữ nguyên 3 mục hiện có); cập nhật docstring đầu file cho khớp (key của các nguồn stock + cả hai provider ảnh AI).
4. `api/src/reels_api/jobs.py` — chỉ sửa điểm gọi tạo ảnh: provider = `config.image_gen_provider()`; key = `source_keys.get(db, provider)`; gọi `imagegen.generate_image(prompt, key, provider)`; `image_source` lấy model theo provider (`config.image_gen_model()` cho gemini, `config.image_gen_cf_model()` cho cloudflare). Toàn bộ luồng còn lại (thứ tự cảnh, bỏ qua cảnh đã có ảnh/clip, đếm image_calls trước mỗi lượt gọi, commit từng cảnh, refresh thumbnail cảnh tiêu đề) giữ nguyên từng dòng.
5. Trang Cài đặt › Nguồn tư liệu — thêm nguồn "Cloudflare" để dán API token, theo đúng pattern của các nguồn hiện có (tìm nơi định nghĩa danh sách nguồn ở api và/hoặc web — grep "pixabay"/"Gemini" trong `api/src` và `web/src` sẽ thấy; nhãn hiển thị "Cloudflare", câu hướng dẫn nhắc API token Workers AI của Cloudflare). Nguồn Gemini giữ nguyên như cũ.

## Fake và test

6. `api/scripts/fake_services.py` — THÊM fake Cloudflare, GIỮ NGUYÊN fake Gemini:
   - Hằng số mới `IMAGE_GEN_CF_KEY = "fake-cloudflare-token"`; state mới `cf_image_gen_mode` (ok|quota|error500), `cf_image_gen_ok_count`, `cf_image_gen_refused`, `cf_image_gen_prompts` (đặt tiền tố cf_ để không lẫn với state Gemini hiện có).
   - Route `POST /cloudflare/client/v4/accounts/{account_id}/ai/run/{model}` (khớp phần đuôi path):
     - Header Authorization khác `Bearer <IMAGE_GEN_CF_KEY>` → 401, envelope `success: false`.
     - Mode quota, hoặc sau khi hết `cf_image_gen_ok_count` → 429, errors chứa chữ "neurons".
     - Prompt chứa chuỗi trong `cf_image_gen_refused` → 200, `success: false`, errors có message kiểu "content policy violation" (đường lỗi từng cảnh).
     - Mode error500 → HTTP 500.
     - Thành công → 200 envelope, `result.image` là base64 của ảnh JPEG VUÔNG 1024×1024 do Pillow vẽ (màu suy từ hash của prompt như fake Gemini). Vuông là cố ý để test đường cắt 9:16.
   - `env()` THÊM: `IMAGE_GEN_CF_API_URL={url}/cloudflare/client/v4`, `IMAGE_GEN_CF_ACCOUNT_ID=test-account`, `IMAGE_GEN_CF_API_KEY=IMAGE_GEN_CF_KEY`. KHÔNG đặt `IMAGE_GEN_PROVIDER` trong env() — mặc định phải là gemini; test Cloudflare tự đặt.
7. `api/tests/conftest.py` — danh sách biến phải dọn THÊM: `IMAGE_GEN_PROVIDER`, `IMAGE_GEN_CF_API_URL`, `IMAGE_GEN_CF_ACCOUNT_ID`, `IMAGE_GEN_CF_API_KEY`, `IMAGE_GEN_CF_MODEL`.
8. `api/tests/test_image_jobs.py` (Gemini) — GIỮ NGUYÊN, không sửa một dòng nào. Đây là lưới chống hồi quy: nó phải xanh trước và sau đợt này.
9. File test MỚI `api/tests/test_image_jobs_cloudflare.py` — theo đúng khuôn của test_image_jobs.py (job chạy in-process trên committed rows), với fixture đặt `IMAGE_GEN_PROVIDER=cloudflare` bằng monkeypatch cho mọi test trong file:
   - Job lấp đầy mọi cảnh thiếu: status done, image_calls = 4 (tiêu đề + 3 cảnh), `image_source` của mọi cảnh là `"ai:@cf/black-forest-labs/flux-1-schnell"`, `cf_image_gen_prompts` ghi đúng các prompt (cảnh tiêu đề dùng dòng đầu tiên của text như Gemini).
   - Ảnh đã lưu của các cảnh, đọc bằng Pillow, có tỉ lệ đúng 9:16 (height × 9 == width × 16, lệch tối đa 1px) — fake trả ảnh vuông nên test này chứng minh đường cắt chạy thật.
   - Cảnh đã có ảnh hoặc clip → bị bỏ qua, 0 lượt gọi.
   - `cf_image_gen_ok_count = 2` → job failed, lỗi chứa "hạn mức", image_calls = 3, hai cảnh đầu giữ ảnh, hai cảnh sau không có.
   - Token sai (monkeypatch `IMAGE_GEN_CF_API_KEY` thành giá trị khác) → job failed ngay, lỗi chứa "không hợp lệ", không cảnh nào có ảnh.
   - Không có token (env rỗng, không lưu trong Cài đặt) → job failed với câu "Chưa có API token Cloudflare nên không tạo được ảnh AI", `cf_image_gen_prompts` rỗng.
   - `IMAGE_GEN_CF_ACCOUNT_ID` rỗng → job failed với câu cấu hình IMAGE_GEN_CF_ACCOUNT_ID, `cf_image_gen_prompts` rỗng.
   - Token lưu qua `source_keys.save(db, "cloudflare", IMAGE_GEN_CF_KEY, user.id)` dùng được khi env rỗng (như test tương ứng của Gemini).
   - Prompt bị từ chối (`cf_image_gen_refused`) → chỉ cảnh đó có `image_error` chứa "từ chối", job vẫn done.
10. `web/playwright.config.ts` — BACKEND_ENV THÊM `IMAGE_GEN_CF_API_URL: ${FAKES_URL}/cloudflare/client/v4`, `IMAGE_GEN_CF_ACCOUNT_ID: "test-account"`, `IMAGE_GEN_CF_API_KEY: "fake-cloudflare-token"` (chỉ để sẵn sàng; test E2E tạo ảnh hiện tại vẫn chạy provider gemini mặc định, giữ nguyên).

## Tài liệu

11. `.env.example` — thêm `IMAGE_GEN_PROVIDER=gemini` kèm comment (đặt `cloudflare` để dùng Cloudflare Workers AI); thêm khối Cloudflare: `IMAGE_GEN_CF_API_KEY` (API token), `IMAGE_GEN_CF_ACCOUNT_ID` (comment: lấy ở dashboard Cloudflare, góc trên bên phải), `IMAGE_GEN_CF_MODEL` (mặc định `@cf/black-forest-labs/flux-1-schnell`). Khối Gemini giữ nguyên.
12. `docs/deployment.md` — thêm các hàng tương ứng cho `IMAGE_GEN_PROVIDER`, `IMAGE_GEN_CF_API_KEY`, `IMAGE_GEN_CF_ACCOUNT_ID`, `IMAGE_GEN_CF_MODEL`; đoạn biến môi trường cho fake nhắc thêm các biến CF.
13. `docs/architecture.md` — mục External Integrations: thêm hàng Cloudflare Workers AI NGANG HÀNG với hàng Gemini (REST `/ai/run`, FLUX.1 schnell, free 10.000 neurons/ngày, ảnh vuông cắt giữa 9:16 phía client) và ghi rõ provider tạo ảnh được chọn bằng `IMAGE_GEN_PROVIDER`, mặc định gemini. Không xoá hàng Gemini.
14. `docs/decisions.md` — THÊM mục mới lên trên cùng, ghi ngày 2026-11-01, tựa đề "Cloudflare Workers AI added as a second AI image provider": Gemini được giữ lại; provider chọn bằng `IMAGE_GEN_PROVIDER`; lý do (free tier Gemini không gồm tạo ảnh; Cloudflare free 10.000 neurons/ngày ≈ 57 ảnh/ngày; tài khoản đã dùng cho web); hệ quả (ảnh Cloudflare gốc vuông 1024×1024 được cắt giữa 9:16 trong imagegen; FLUX.1 schnell giấy phép Apache-2.0, không SynthID; mỗi provider có key riêng ở trang Nguồn tư liệu). KHÔNG sửa các mục cũ.
15. `docs/specs/ai-scene-images/brief.md` — thêm đoạn ngắn ở cuối file: "Cập nhật 2026-11-01: thêm Cloudflare Workers AI làm provider thứ hai bên cạnh Gemini — xem docs/decisions.md". Không viết lại nội dung cũ.

## Không được đụng

- Nhánh Gemini trong `imagegen.py` (mọi câu chữ lỗi, promptFeedback, generationConfig), fake Gemini, test Gemini.
- Endpoint `POST /videos/{id}/image`, `videos.py`, trang video phía web, `uploads.py`, migrations.
- File `.env`: không đọc, không sửa. Không gọi API Cloudflare/Gemini thật trong test — chỉ qua fake.

## Thứ tự làm và kiểm chứng

1. Baseline trước khi sửa: chạy `cd api && .venv/bin/python -m pytest tests/test_image_jobs.py -q` — phải xanh. Nếu đang đỏ sẵn thì DỪNG và báo cáo, không sửa chen.
2. Thêm fake Cloudflare + file test Cloudflare → chạy thấy đỏ (chưa có nhánh cloudflare).
3. Implement config/imagegen/source_keys/jobs/trang nguồn → chạy lại tới khi cả hai file test ảnh đều xanh.
4. Chạy toàn bộ: `.venv/bin/python -m pytest -q` và `.venv/bin/ruff check src tests scripts` (trong `api/`).
5. Nếu có sửa phía web: `cd web && npm run lint && npm run typecheck`; E2E liên quan giữ xanh.
6. KHÔNG commit, KHÔNG merge — để nguyên working tree cho chủ repo duyệt.

## Báo cáo — 3 phần đúng quy ước repo

- **Đã làm:** từng file thay đổi kèm một dòng lý do.
- **Đã kiểm chứng:** liệt kê lệnh ĐÃ CHẠY THẬT và kết quả thật (số test pass/fail, gồm cả baseline ở bước 1). Chưa chạy cái gì thì nói rõ là chưa chạy.
- **Rủi ro còn lại:** những gì chưa kiểm chứng được ở local — đặc biệt: hợp đồng API Cloudflare thật chưa được gọi thử (không có token trong môi trường test); chủ repo sẽ đặt `IMAGE_GEN_PROVIDER=cloudflare` và test tay bằng token thật sau.
