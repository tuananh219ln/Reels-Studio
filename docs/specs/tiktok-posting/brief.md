# Brief: Đăng TikTok bằng API (issue #46) — OAuth theo từng thành viên + Content Posting API

## 0. Bàn giao

- Model: Sonnet, effort medium, KHÔNG dùng subagent. Đọc `AGENTS.md` trước khi sửa; không commit/merge; không đụng production; test chỉ qua fake services, không gọi TikTok thật.
- Làm theo đúng thứ tự §8. Chạy pytest liên quan sau mỗi bước; bước nào đỏ thì dừng và báo.
- Báo cáo 3 phần khi xong: Done / Verified (lệnh thật đã chạy) / Remaining risks.

## 1. Vấn đề

Hiện tại TikTok là đăng tay hoàn toàn: `routes_tiktok.py` chỉ ghi lại bài đã đăng trong app TikTok (docstring ghi rõ "posting through TikTok's API waits for issue #46"), `metrics.py` bỏ qua bài TikTok, gắn giỏ hàng làm trong app TikTok. Việc đăng tay làm chậm vòng đăng bài và không quay được video demo cho hồ sơ duyệt app.

Phía TikTok đã sẵn sàng (làm 07/11/2026): app developer "Reels Studio" (org Reels Studio) đã tạo, cấu hình đã lưu — Login Kit + Content Posting API, Direct Post bật, scope đúng 3 cái `user.info.basic` / `video.upload` / `video.publish`, Redirect URI `https://reels.quangdang.xyz/api/tiktok/oauth/callback`, 3 URL (web/terms/privacy) đã verify bằng file chữ ký. Còn thiếu duy nhất video demo để nộp duyệt — video đó phải quay luồng tích hợp THẬT trong Sandbox, nên code này là điều kiện tiên quyết.

Mục tiêu của brief: thành viên tự kết nối tài khoản TikTok của mình bằng OAuth, rồi đăng video (bản platform = tiktok, đã render MP4) từ trong app qua Content Posting API — chế độ nháp là mặc định, đăng thẳng là lựa chọn thêm.

## 2. Quyết định (ghi vào docs/decisions.md, mục mới trên cùng, ghi ngày)

1. **OAuth theo từng thành viên, token là của từng người** — đúng mô hình "tool dùng chung, tiền nhận riêng": mỗi thành viên chỉ đăng được lên tài khoản TikTok CỦA MÌNH. Đơn vị sở hữu vẫn là từng Publication (video × nền tảng × tài khoản) như hiện tại.
2. **Kết nối gắn vào `AffiliateAccount` platform = tiktok sẵn có** (bảng mới `tiktok_connections` trỏ vào nó), để luồng ghi tay cũ và luồng API mới dùng chung một khái niệm "tài khoản TikTok của thành viên"; Publication vẫn tham chiếu `affiliate_account_id` như hiện tại.
3. **Chế độ nháp (`video.upload`) là mặc định**; đăng thẳng (`video.publish`) là lựa chọn thêm. Lý do: app chưa qua audit thì Direct Post bị TikTok khóa ở riêng tư (xem §3) và giỏ hàng TikTok Shop vẫn phải gắn trong app TikTok — nháp là đường dùng thật được ngay.
4. **Video AI luôn khai báo `is_aigc = true`** khi đăng thẳng (video của app là nội dung AI; TikTok bắt buộc gắn nhãn, gắn nhãn không bị phạt phân phối).
5. **Không đọc số liệu TikTok về app trong đợt này** (không xin scope `video.list`): số TikTok vẫn đo tay như hiện tại. Không gắn giỏ hàng qua API (TikTok không cho — xem §3).
6. **Client Key/Secret của app developer để trong `.env`** (không theo từng thành viên — đây là danh tính của APP, không phải của người dùng), theo mẫu `config.py` hiện có; cập nhật `docs/deployment.md` trong cùng PR.

## 3. Sự thật về TikTok API (đã kiểm chứng 07/11/2026 — bám đúng, đừng tự chế biến thể khác)

- OAuth 2.0 (Login Kit): trang ủy quyền `https://www.tiktok.com/v2/auth/authorize/` (tham số `client_key`, `scope`, `response_type=code`, `redirect_uri`, `state`); đổi code và làm mới token đều ở `POST https://open.tiktokapis.com/v2/oauth/token/`. Redirect URI phải khớp TUYỆT ĐỐI với URI đã đăng ký (`https://reels.quangdang.xyz/api/tiktok/oauth/callback`), https, không query string.
- Access token sống 24 giờ; refresh token sống 365 ngày và **bị xoay vòng mỗi lần làm mới** (TikTok trả refresh token MỚI — phải lưu đè cả hai token sau mỗi lần refresh, mất refresh token mới là mất kết nối).
- Thông tin người dùng: `GET https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,display_name,username` (scope `user.info.basic`).
- Đăng bài: `POST /v2/post/publish/inbox/video/init/` (nháp, scope `video.upload`) và `POST /v2/post/publish/video/init/` (đăng thẳng, scope `video.publish`); trạng thái ở `POST /v2/post/publish/status/fetch/` (trạng thái cuối thành công là `PUBLISH_COMPLETE`; phía nháp, video tới hộp thư người dùng là hoàn tất). Trước khi đăng thẳng phải gọi `POST /v2/post/publish/creator_info/query/` để lấy `privacy_level_options` và các cờ disable comment/duet/stitch của tài khoản đó — chỉ cho chọn mức riêng tư TikTok trả về.
- Upload file (source `FILE_UPLOAD`): init trả `publish_id` + `upload_url`; client PUT nội dung theo chunk 5–64 MB (file nhỏ hơn 64 MB thì 1 chunk = cả file; MP4 của app ~12 MB nên thường 1 chunk), khai báo `video_size`, `chunk_size`, `total_chunk_count` lúc init.
- Giới hạn: ~6 lần init/phút/token; đăng thẳng ~15 bài/ngày/tài khoản (dùng chung mọi app). Gặp rate limit thì ghi lỗi và dừng, KHÔNG retry vòng lặp.
- **Chưa qua audit**: Direct Post chỉ đăng được ở `privacy_level = SELF_ONLY`, chỉ lên tài khoản đang để private, tối đa 5 người dùng/24 giờ. Lỗi TikTok trả về trong trường hợp này phải được dịch thành thông báo dễ hiểu cho thành viên (kèm chi tiết gốc ở `error_detail`), không nuốt lỗi.
- **Giỏ hàng TikTok Shop KHÔNG gắn được qua Content Posting API** — đừng thiết kế chỗ nào hứa hẹn gắn giỏ qua API. Chế độ nháp giữ nguyên lợi thế hiện tại: thành viên mở app TikTok, gắn giỏ + nhãn AI rồi bấm đăng.
- Sandbox: cổng developer có môi trường Sandbox với bộ Client Key/Secret RIÊNG và phải thêm tài khoản TikTok đích vào sandbox. Code không cần biết sandbox là gì — chỉ cần credentials lấy từ env (§4.1), để khi quay video demo chỉ việc trỏ env sang credentials Sandbox.

## 4. Thiết kế

### 4.1 Cấu hình (`config.py`, theo đúng mẫu sẵn có)

- `tiktok_api_url()` = `read_env("TIKTOK_API_URL") or "https://open.tiktokapis.com"` (kèm comment chuẩn "Overridable only so tests…" như các hàm khác) — fake service dùng biến này để chen vào.
- `tiktok_client_key()` = `read_env("TIKTOK_CLIENT_KEY")`; `tiktok_client_secret()` = `read_env("TIKTOK_CLIENT_SECRET")`. Secret không bao giờ xuất hiện trong response, payload trả về web, hay log.
- Chưa cấu hình credentials mà bấm kết nối/đăng thì báo lỗi rõ ràng kiểu các lỗi cấu hình sẵn có ("Chưa cấu hình TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET trong .env").

### 4.2 Client TikTok (`api/src/reels_api/tiktok.py`, module mới, theo mẫu `shopee.py`/`facebook.py`)

- `TikTokError(message, detail)` — message hiển thị cho thành viên, detail giữ nguyên trả lời của TikTok để debug.
- Hàm: `authorize_url(state)`, `exchange_code(code)`, `refresh(refresh_token)`, `user_info(access_token)`, `creator_info(access_token)`, `init_inbox(access_token, size, chunk_size, chunks)`, `init_direct(access_token, post_info, size, chunk_size, chunks)`, `upload_chunks(upload_url, data, chunk_size)`, `publish_status(access_token, publish_id)`.
- Mọi lời gọi qua urllib với timeout như các client sẵn có; base URL lấy từ `config.tiktok_api_url()`; host ủy quyền `www.tiktok.com` để cố định (không qua fake — test kiểm tra URL được tạo ra, không gọi thật).
- Ánh xạ lỗi: token hết hạn/không hợp lệ (TikTok trả `error` dạng `access_token_invalid` / HTTP 401) → thông báo "Kết nối TikTok đã hết hạn, hãy kết nối lại"; rate limit → "TikTok đang giới hạn tốc độ, thử lại sau"; các lỗi còn lại → message ngắn + detail gốc.

### 4.3 Kết nối OAuth (bảng mới + routes)

- Migration mới (kiểm tra thư mục versions của Alembic, lấy số tiếp theo — không đoán): bảng `tiktok_connections`: `id`, `owner_id` (FK users, index), `affiliate_account_id` (FK affiliate_accounts, UNIQUE — một tài khoản TikTok một kết nối), `open_id` (String 100, UNIQUE), `username` (String 100), `display_name` (String 200), `avatar_url` (Text, nullable), `access_token_encrypted` (Text), `refresh_token_encrypted` (Text), `access_expires_at`, `refresh_expires_at` (DateTime tz), `scopes` (String 200), `created_at`, `updated_at`, `last_error` (Text, nullable). Token mã hóa bằng `crypto.py` như Fanpage token; không có cột nào chứa token thô.
- Bảng phụ `tiktok_oauth_states`: `state_hash` (PK, hash của state — theo mẫu băm mã của `McpAuthorization`), `user_id` (FK users), `expires_at` (10 phút). State không lưu thô.
- Routes (thêm vào `routes_tiktok.py` hoặc router riêng `routes_tiktok_oauth.py` nếu gọn hơn):
  - `GET /api/tiktok/oauth/start` (cần đăng nhập thành viên): tạo state ngẫu nhiên, lưu hash, trả về (hoặc redirect 302 tới) URL ủy quyền TikTok với scope đúng 3 scope đã đăng ký và redirect_uri đã đăng ký.
  - `GET /api/tiktok/oauth/callback`: kiểm tra state còn hạn và thuộc về đúng thành viên đang đăng nhập (cookie phiên đi qua cùng tên miền — callback bị mất phiên thì báo lỗi rõ ràng, không tạo kết nối mồ côi); đổi code lấy token; gọi `user_info`; tìm `AffiliateAccount` platform = tiktok của CHÍNH thành viên có `profile_url`/username khớp, không có thì tạo mới (name = display_name, `profile_url = https://www.tiktok.com/@<username>`, active); tạo/cập nhật `tiktok_connections` (một open_id thuộc về đúng một thành viên — open_id đã gắn với thành viên khác thì báo lỗi, không giành); cuối cùng redirect 302 về web (`/settings/affiliate?tiktok=connected` khi thành công, `?tiktok=error&message=...` khi thất bại — khớp với route Cài đặt tài khoản affiliate hiện có, kiểm tra lại đường dẫn thật trong web).
  - `DELETE /api/tiktok/connections/{id}`: chỉ chủ kết nối; xóa hàng kết nối (tài khoản affiliate và các Publication cũ giữ nguyên). Gọi thêm endpoint thu hồi của TikTok nếu thuận tiện nhưng lỗi thu hồi không chặn việc xóa ở phía app.
  - Payload trạng thái kết nối cho web: username, display_name, avatar_url, hạn access/refresh token, `last_error` — KHÔNG kèm token dưới bất kỳ dạng nào (kể cả đuôi token).
- Làm mới token: hàm dùng chung trong `tiktok.py` hoặc module kết nối — khi access token còn dưới 5 phút là hết hạn thì refresh TRƯỚC khi dùng, lưu đè cả access token mới lẫn refresh token mới + hạn mới. Refresh thất bại (TikTok thu hồi) → ghi `last_error`, đánh dấu kết nối cần nối lại, job đang chạy báo lỗi "hãy kết nối lại TikTok".

### 4.4 Đăng bài (route + job worker)

- Route `POST /api/tiktok/videos/{video_id}/publish`, body `{account_id, mode: "draft" | "direct", privacy_level?: string}`. Kiểm tra như `record_post` hiện tại, cộng thêm: tài khoản là TikTok AffiliateAccount CỦA thành viên gọi và có `tiktok_connections` còn hiệu lực; video `platform = "tiktok"` và đã có MP4; chưa có Publication TikTok nào của video đang `pending` (index `uq_publications_pending` đã chặn — dịch lỗi trùng thành thông báo dễ hiểu); mode direct mà thiếu `privacy_level` thì mặc định `SELF_ONLY`. Tạo `Publication(platform = "tiktok", status = "pending", affiliate_account_id = account, created_by_id = me)` + cột mới `publish_mode` (migration: String 16, nullable, chỉ dùng cho TikTok: `draft` | `direct`) và Job kind mới `tiktok_publish` (String 16 chứa vừa), `publication_id` trỏ vào Publication vừa tạo (cột `Job.publication_id` sẵn có). Bấm đăng là đăng NGAY (không hẹn giờ cho TikTok trong đợt này).
- Worker xử lý `tiktok_publish` trong vòng lặp job hiện có (theo mẫu publish của Facebook):
  1. Nạp MP4 từ storage theo `video.mp4_key`; refresh token nếu sắp hết hạn.
  2. Mode direct: gọi `creator_info` trước; `privacy_level` người dùng chọn không nằm trong `privacy_level_options` thì fail job với thông báo nêu rõ các mức TikTok cho phép.
  3. Init đúng mode → **lưu `publish_id` vào `Publication.remote_id` và commit NGAY, trước khi upload chunk** (bài học từ luồng Facebook: thử lại phải tiếp tục đúng bài đó, không đăng trùng bài thứ hai). Job thử lại (retry_of) với Publication đã có `remote_id` thì gọi `publish_status` trước: đã hoàn tất thì chốt trạng thái, đang chạy thì chờ tiếp, TikTok báo publish_id không tồn tại/thất bại hẳn mới init lại.
  4. Upload chunk: tính `chunk_size`/`total_chunk_count` theo §3 (file ≤ 64 MB → 1 chunk); PUT từng chunk vào `upload_url`.
  5. Poll `publish_status` mỗi ~10 giây, tối đa ~5 phút: `PUBLISH_COMPLETE` (hoặc trạng thái xác nhận đã vào hộp thư ở mode nháp) → `Publication.status = "published"`, `published_at = now`, job done. Quá hạn poll mà vẫn đang xử lý → job FAILED với lỗi rõ ràng, Publication GIỮ `pending` + `remote_id` để lần thử lại đi tiếp đúng bài (không tạo Publication mới). Lỗi TikTok khác → job failed, `error` cho thành viên + `error_detail` nguyên văn.
  - Nội dung đăng: `title` = caption của video + hashtag nối cách nhau bằng dấu cách (cắt ở 2.200 ký tự theo giới hạn TikTok); mode direct: `post_info` gồm title, `privacy_level`, `disable_comment/duet/stitch = false`, **`is_aigc = true`** (cứng cho mọi video của app — video do AI làm). Mode nháp không có post_info — caption do thành viên chốt trong app TikTok như hiện nay.
- Gắn link bài sau đăng: `POST /api/tiktok/posts/{post_id}/url {url}` — dùng lại `_post_url` của `routes_tiktok.py`, chỉ người tạo Publication, chỉ khi Publication platform = tiktok và chưa có `post_url`; phục vụ cả hai mode (TikTok API không trả URL bài đăng cuối vì app không có scope `video.list`).
- KHÔNG đổi gì ở luồng ghi tay (`record_post`, `remove_post`) và KHÔNG để `metrics.py` chạm vào Publication do API tạo (nó đã bỏ qua TikTok — giữ nguyên).

### 4.5 Web

- Cài đặt › Tài khoản affiliate: mỗi tài khoản TikTok của thành viên có thêm trạng thái kết nối API — chưa kết nối thì nút **"Kết nối TikTok"** (mở `/api/tiktok/oauth/start`), đã kết nối thì hiện avatar + @username + hạn token + nút **"Ngắt kết nối"**; kết nối hết hạn/có `last_error` thì hiện cảnh báo + nút kết nối lại. Trạng thái `?tiktok=connected|error` từ callback được hiển thị thành thông báo trên trang này.
- Trang video (bản TikTok, đã có MP4): nút **"Đăng lên TikTok"** cạnh form "Đã đăng tay" hiện tại — chọn tài khoản TikTok ĐÃ KẾT NỐI của chính mình, chọn chế độ (**Nháp** mặc định / **Đăng thẳng**), nếu đăng thẳng thì chọn mức riêng tư kèm ghi chú rõ: "App chưa qua duyệt TikTok: hiện chỉ đăng được ở chế độ riêng tư (Chỉ mình tôi) lên tài khoản đang để private". Trạng thái job + lỗi hiển thị như các job khác; Publication tạo ra hiện nhãn chế độ ("Nháp TikTok" / "Đăng thẳng") và ô gắn link bài đăng khi chưa có `post_url`.

## 5. Không làm

- Không xin thêm scope (không `video.list`, không Display API), không đọc view/comment/số liệu TikTok về app.
- Không gắn giỏ hàng TikTok Shop qua API (TikTok không hỗ trợ qua Content Posting API).
- Không hẹn giờ đăng TikTok, không hàng đợi theo Page như Facebook (`page_queue` là của Facebook).
- Không sửa luồng ghi tay, không sửa hành vi đăng Facebook, không đổi `metrics.py`.
- Không lưu token thô ở bất cứ đâu; không đưa Client Secret hay token ra frontend/log/response.
- Không gọi TikTok thật trong test; không đụng production.

## 6. Kiểm thử

- Trước tiên chạy pytest affiliate + tiktok hiện có (vd `api/tests/test_affiliate*.py` và test chạm `routes_tiktok`) — đã đỏ sẵn thì dừng và báo, không xây tiếp trên nền đỏ.
- Fake TikTok trong `api/scripts/fake_services.py` theo mẫu fake Shopee/Facebook sẵn có (đạt được qua `TIKTOK_API_URL`): endpoint token (cấp + refresh có xoay vòng refresh token), user info, creator_info, inbox/video init, upload chunk, status fetch (điều khiển được trạng thái trả về).
- Test mới (gợi ý `api/tests/test_tiktok_api.py`): (1) authorize URL đúng client_key/scope/redirect_uri/state; (2) callback thành công → token lưu MÃ HÓA (đọc thô cột DB không thấy token), AffiliateAccount được tạo/gắn đúng chủ, connection trỏ đúng; (3) callback sai state/hết hạn → lỗi, không tạo connection; (4) open_id của người khác → từ chối; (5) refresh trước khi đăng khi token sắp hết hạn + lưu refresh token mới; (6) đăng nháp: init → remote_id lưu TRƯỚC upload → poll tới hoàn tất → Publication published + publish_mode = draft; (7) đăng thẳng: post_info có `is_aigc = true`, title = caption + hashtags, privacy ngoài `privacy_level_options` → fail rõ ràng; (8) thử lại job với remote_id đã có → gọi status trước, KHÔNG init lần hai; (9) tài khoản của người khác / chưa kết nối → bị chặn ở route publish; (10) lỗi TikTok (hết hạn token, rate limit, SELF_ONLY khi chưa audit) → message thành viên đúng ánh xạ §4.2; (11) không có credentials trong env → lỗi cấu hình rõ ràng.
- Web: typecheck + lint sau khi sửa.

## 7. Tài liệu và việc tay của chủ sau khi merge

- `docs/decisions.md`: ghi 6 quyết định ở §2. `docs/deployment.md`: thêm `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_API_URL` (mặc định, chỉ đổi cho test/fake) + ghi chú Sandbox dùng bộ credentials riêng trong cùng 2 biến đầu khi quay demo.
- Chủ tự làm sau merge (không phải việc của coding agent): điền Client Key/Secret (Production) vào `.env` production, restart api + worker; kết nối tài khoản @anlanhsk trong Cài đặt › Tài khoản affiliate; đăng thử 1 video chế độ NHÁP và mở app TikTok kiểm tra video đã vào hộp thư; sau đó mới quay video demo bằng credentials Sandbox để nộp duyệt app TikTok.

## 8. Thứ tự làm

1. (a) `config.py` + `tiktok.py` + fake TikTok + test client.
2. (b) Migration (2 bảng + cột `publications.publish_mode`) + model + OAuth routes + test OAuth.
3. (c) Route publish + xử lý job `tiktok_publish` trong worker + endpoint gắn link bài + test đăng bài.
4. (d) Web: trạng thái kết nối ở Tài khoản affiliate + nút Đăng lên TikTok ở trang video.
5. (e) decisions.md + deployment.md. Chạy lại toàn bộ test chạm tới sau mỗi bước.
