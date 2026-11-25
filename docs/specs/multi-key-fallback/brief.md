# Brief Reels Studio — Nhiều key API + tự đổi key khi hết hạn mức (key chung + key riêng) + hạn mức theo từng key

> **Việc MỚI, brief riêng** — user chốt tối 18/11/2026, review + gộp tính năng "Hạn mức dịch vụ AI" (nhánh `feature/ai-service-usage`) cùng ngày. Cho phép thêm nhiều key API cho mỗi dịch vụ lời đọc (ElevenLabs, Gemini, VieNeu): hết key này thì tự dùng key khác; key chung vẫn dùng chung cả team; mỗi người được thêm key riêng ở "Key API của tôi", chỉ dùng cho video của mình, làm dự phòng khi key chung hết hạn mức. Thẻ hạn mức trên Nguồn tư liệu hiện số dùng **theo từng key**, không chỉ theo dịch vụ.
>
> Thi công theo lệ team: đọc AGENTS.md + docs/decisions.md + docs/decisions/ trước (quyết định mới là file riêng trong docs/decisions/, KHÔNG append vào docs/decisions.md); TDD, test bằng fake services, báo cáo 3 phần, không tự merge.
>
> **Nhánh:** `feature/multi-key-fallback` (theo AGENTS.md là `feature/...`, không phải `feat/...`). Việc này dựng trên tính năng hạn mức nên **tạo nhánh từ main sau khi PR `feature/ai-service-usage` đã merge**. Nếu PR đó chưa merge lúc bắt đầu thì dừng và hỏi user (không sửa chung vùng `jobs.py` / `routes_settings.py` / trang Nguồn tư liệu với một nhánh đang mở).

> **Cập nhật 18/11 (lúc code):** user cho làm ngay từ main, chưa chờ PR `ai-service-usage`. Đã làm Phần 1–5. **Phần 6 (hạn mức theo từng key) để lại** tới khi PR đó merge, vì bảng `ai_service_calls` chưa có trên main. Lúc code đã đổi 2 điểm so với brief: key chính vẫn nằm trong AppSetting `source_keys` (không chuyển sang bảng mới, nên không cần migrate dữ liệu); bảng `api_keys` chỉ giữ key dự phòng của team và key riêng. ElevenLabs vẫn chỉ đổi key khi gặp 402 hoặc body có chữ "quota" (chưa thêm "credit"/"balance"). Xem 2 file quyết định ngày 2026-11-18.

> **Cập nhật 18/11 (sau khi xem bản đầu), thay các điểm bên dưới:** user **bỏ key riêng** ("Key API của tôi", trang, cột `user_id`, scope `mine`): chỉ còn key dự phòng của team. Đổi key **cả khi key sai/không được phép** (401/403), không chỉ khi hết hạn mức (Nguyên tắc 3 bỏ); key nào lỗi thì **báo ngay tại dòng của key đó** (lý do + giờ VN, cột `api_keys.error`/`error_at`, key chính trong AppSetting `source_key_errors`), tự xoá khi key đọc được lại. Lỗi server/mạng/giới hạn mỗi phút vẫn không đổi key. Đồng thời gộp "Mô hình AI" và "Nguồn tư liệu" thành một tab "AI và nguồn tư liệu", chia nhóm đóng mở được. Xem `docs/decisions/2026-11-18-tts-key-fallback.md` và `2026-11-18-ai-and-sources-settings.md`.

## Điều phải chốt TRƯỚC khi code (xung đột với quyết định đã ghi)

- **Key riêng ngược với quyết định 2026-11-09 "settings-mine-and-shared"**, ghi rõ: *"no member has keys or a model of their own"*. Brief này đảo điểm đó. **Owner (namtc) đã đồng ý trong chat ngày 18/11/2026.** PR vẫn phải thêm file `docs/decisions/2026-11-18-personal-api-keys.md` ghi rõ nó thay điểm nào của quyết định 09/11 và vì sao (Gemini miễn phí 10 lượt/ngày không đủ cho 4 video format mới/ngày).
- **Quyết định 2026-11-16 "gemini-tts"** nói app "không tự đổi giọng" khi hết lượt ngày và job lỗi ngay. Đợt này app vẫn **không đổi giọng**, chỉ đổi **key** của cùng dịch vụ; ghi rõ điều này trong file quyết định mới.
- **Quyết định 2026-11-18 "ai-service-usage"** nói app đếm lượt Gemini chỉ để hiển thị, "không dừng hay đổi giọng theo số đếm". Vẫn giữ: đổi key dựa vào **tín hiệu hết hạn mức nhà cung cấp trả về**, không dựa vào số app tự đếm.

## Nguyên tắc xuyên suốt

1. **Key chung vẫn là mặc định.** Lời đọc luôn thử key chung trước; key riêng chỉ là dự phòng khi key chung hết hạn mức — không thay thứ tự này.
2. **Key riêng theo người dùng**: key riêng của ai chỉ dùng cho video của người đó (chủ video = `videos.created_by_id`); user khác không thấy, không sửa, không dùng cho video của họ.
3. **Hết hạn mức mới đổi key, lỗi khác thì không.** Chỉ đổi key khi gặp đúng tín hiệu hết hạn mức (bảng ở Phần 3). Key sai, lỗi mạng, lỗi server thì báo lỗi như hiện tại, không lặng lẽ dùng key khác.
4. **Key không bao giờ hiện lại.** Lưu mã hoá (`crypto`); API/web không trả key về trình duyệt, chỉ nhãn + "…" + 4 ký tự cuối (không hiện ký tự nào cho key dưới 12 ký tự, như lệ 09/11) + nguồn (chung/riêng/.env). Log cũng chỉ ghi như vậy.
5. **Không đổi hành vi khi chỉ có 1 key.** Team chỉ dùng 1 key chung thì mọi thứ chạy y cũ: cùng thông báo lỗi, cùng số lượt gọi, không chậm thêm.

## Bối cảnh và hiện trạng (kiểm chứng trong code `origin/main` + nhánh `feature/ai-service-usage`, 18/11)

- `api/src/reels_api/source_keys.py`: mỗi dịch vụ **1 key chung**, trong AppSetting `source_keys` = `{tên: key mã hoá}`, cho 7 tên (pixabay, pexels, unsplash, gemini, cloudflare, elevenlabs, vieneu). Key đã lưu thắng `.env`. `get()` trả 1 chuỗi; `origin()` trả saved/unreadable/env/None; `save()` nhận 1 chuỗi (≤300 ký tự, không khoảng trắng; chuỗi rỗng = xoá). Đổi key chung được ghi vào Lịch sử của tab (edit history, `settings_log`).
- **Key `gemini` dùng chung cho 3 việc**: lời đọc Gemini, tạo ảnh AI (`jobs.py` run_image_job / run_article_image_job, `image_providers.py`) và sửa ảnh (`run_image_edit_job`). Đợt này chỉ lời đọc được nhiều key (Phần 5).
- **Key `elevenlabs` dùng thêm cho tách lời video mẫu** (Speech-to-Text, `reference.py`): đợt này giữ 1 key (key chung đầu tiên).
- **Key VieNeu nhập ở Cài đặt › Mô hình AI**, không phải Nguồn tư liệu (quyết định 2026-11-07). ElevenLabs và Gemini ở Nguồn tư liệu.
- `api/src/reels_api/tts.py`: `synthesize(text, key, voice_id, speed)` nhận 1 key. Lỗi:
  - ElevenLabs `_http_error`: body có "quota" **hoặc** 402 → hết ký tự (được xét **trước** 401). Thực tế ElevenLabs báo hết ký tự bằng **HTTP 401 `{"detail":{"status":"quota_exceeded"}}`** (fake service `fake_services.py:892` và `test_voice.py:348` mô phỏng đúng thế), nên "401 = key sai" là sai với ElevenLabs.
  - Gemini `_gemini_error` + `_gemini_daily_limit`: 429 hết lượt ngày → lỗi ngay; 429 theo phút → chờ rồi thử lại (`GEMINI_RETRIES = 3`).
  - VieNeu `_vieneu_error`: 401 key sai; 429 có "trial" → key dùng thử hết lượt ngày; 429 khác → giới hạn lượt; 402 hoặc "credit"/"quota"/"balance" → hết credit; 403 chưa có gói.
- `api/src/reels_api/jobs.py` `make_voices()` gọi `synthesize(text, source_keys.get(db, tts_key_name(voice)), ...)`. **`make_voices` có 4 nơi gọi**: render (`run_render_job`), "Tạo giọng thật" (`run_voice_job`), `auto_photos.py`, `rework.py`. Đổi key phải làm trong `make_voices` (hoặc hàm nó gọi) để cả 4 đường đều có.
- **Mọi video đều có chủ**: `Video.created_by_id` là NOT NULL; `Job.created_by_id` cũng NOT NULL. Không tìm thấy job định kỳ nào kiểu "dựng 17:30" trong `api/src`; video do việc tự động tạo vẫn có `created_by_id`.
- Nhánh `feature/ai-service-usage` (chưa merge): bảng `ai_service_calls` (service, kind = image/edit/voice, created_at; giữ 35 ngày); `service_usage.record()` ghi **trước** mỗi lượt gọi Gemini/Cloudflare (lời đọc Gemini ghi trong `make_voices`); `GET /settings/sources/usage` trả thẻ ElevenLabs (số ký tự đã dùng/giới hạn/ngày làm mới từ `/v1/user/subscription`, cache 5 phút theo hash key), Cloudflare (neurons hôm nay) và Gemini (số lượt app tự đếm hôm nay theo ngày giờ Thái Bình Dương). Web: `ServiceUsage.tsx` trên trang Nguồn tư liệu. Tất cả hiện **theo dịch vụ, 1 key**.
- Sự cố khơi ra việc này (18/11): key Gemini miễn phí giới hạn **10 lượt/ngày** (3 lượt/phút), làm mới 0h giờ Thái Bình Dương = 15h giờ VN (14h khi Mỹ theo giờ mùa hè). Lô 240–245 hết lượt giữa chừng (render 242/243/245 lỗi). 4 video format mới/ngày cần ~16–20 lượt Gemini. ElevenLabs Starter 30.000 credits/tháng; 6 video/ngày ≈ 7–12k ký tự/ngày.

## Phần 1 — Key chung: nhiều key cho mỗi dịch vụ lời đọc

- ElevenLabs và Gemini (Nguồn tư liệu) và VieNeu (Mô hình AI — giữ đúng trang hiện tại) được thêm **nhiều key**. Mỗi key có nhãn tự đặt (mặc định "Key 1", "Key 2"…) + "…" 4 ký tự cuối.
- Thứ tự thử = thứ tự danh sách; đổi thứ tự bằng **nút lên/xuống** (đơn giản, dễ test E2E hơn kéo thả).
- Key chung đang lưu trong `source_keys` thành key đầu tiên khi chuyển đổi — không bắt team nhập lại.
- Mọi thành viên sửa được key chung như hiện tại; mỗi lần thêm/xoá/đổi nhãn/đổi thứ tự key chung ghi vào Lịch sử của tab như lệ 09/11 ("đã thêm khoá …k3P1", "đã xoá khoá …k3P1", "đã đưa khoá …k3P1 lên đầu").
- **Key chung đầu tiên của Gemini vẫn là key tạo ảnh và sửa ảnh; key chung đầu tiên của ElevenLabs vẫn là key tách lời video mẫu** (Phần 5).

## Phần 2 — Key riêng: trang "Key API của tôi" dưới "Của tôi"

- Trang mới trong Cài đặt, nhóm "Của tôi", tên "Key API của tôi" (`web/src/app/(app)/settings/my-keys/` hoặc theo cách các tab Cài đặt hiện có được khai báo). Theo quyết định 09/11 không gắn tag hay banner "của ai" — nhóm "Của tôi" đã nói điều đó; một dòng mô tả ngắn là đủ: key ở đây chỉ dùng cho video của bạn, sau khi key chung đã hết hạn mức. (Không nhấn mạnh "người khác không xem được" trong UI.)
- Mỗi người thêm nhiều key cho ElevenLabs, Gemini, VieNeu; cùng nút lên/xuống, xoá, đổi nhãn.
- Key riêng chỉ dùng cho video có `created_by_id` là người đó. API chỉ trả key của người đang đăng nhập; không có endpoint nào liệt kê key riêng của người khác.
- Key riêng không ghi vào Lịch sử chung của team.
- Người chưa thêm key riêng thì mọi thứ chạy như cũ.

## Phần 3 — Luật đổi key khi tạo lời đọc (phần quan trọng nhất)

- **Thứ tự thử** cho một cảnh (video của user U, dịch vụ S): (1) key chung của S theo danh sách → (2) key riêng của U cho S theo danh sách → (3) key `.env` của S nếu khác mọi key ở trên. Không có key nào thì báo "Chưa có key …" như hiện tại.
- **Chủ video = `video.created_by_id`**, không phải người bấm render (`job.created_by_id`). Owner đã chốt (18/11/2026): video của người nào thì render bằng key riêng của người đó, bất kể ai bấm render; ghi vào file quyết định.
- **Tín hiệu đổi key (và chỉ những tín hiệu này):**

  | Dịch vụ | Đổi key khi | Không đổi key |
  | --- | --- | --- |
  | Gemini | 429 và `_gemini_daily_limit(body)` | 429 theo phút (giữ chờ + `GEMINI_RETRIES` trên cùng key), 401/`API_KEY_INVALID`, 403, 404, 400, ≥500, lỗi mạng |
  | ElevenLabs | 402, hoặc body có "quota"/"quota_exceeded" (kể cả khi kèm **HTTP 401**), "credit", "balance" | 401 không kèm các chữ trên, 404, 429 theo phút, ≥500, lỗi mạng |
  | VieNeu | 429 có "trial" (hết lượt ngày), 402 hoặc "credit"/"quota"/"balance" | 401, 403, 429 khác, 400, ≥500, lỗi mạng |

  Cách làm gọn: `TtsError` mang thêm một cờ (vd `exhausted: bool`) do chính `_http_error`/`_gemini_error`/`_vieneu_error` đặt, thay vì so lại chuỗi lỗi ở `jobs.py`. Các nhánh "credit"/"balance" mới của ElevenLabs là mở rộng `_http_error`; thông báo cũ giữ nguyên.
- **Nhớ key đã hết trong một lượt `make_voices`**: key đã báo hết hạn mức thì bỏ qua cho các cảnh sau trong cùng job. Job sau thử lại từ đầu. Đợt này **không** lưu trạng thái hết hạn mức qua các job.
- **Ghi log mỗi lần đổi key** (log job): dịch vụ, key hết (nhãn + …4 ký tự cuối), key sẽ thử tiếp. Không ghi key.
- **Hết mọi key**: job lỗi như hiện tại, thông báo nói rõ đã thử hết N key của dịch vụ và giờ làm mới dự kiến (Gemini: 0h giờ Thái Bình Dương, hiện bằng giờ VN; ElevenLabs/VieNeu: không đoán giờ, nói "khi gói được làm mới hoặc nạp thêm"). Gợi ý chọn giọng dịch vụ khác giữ như thông báo hiện tại.
- Đếm lượt (Phần 6) ghi cho **từng lần gọi, kể cả lần bị từ chối**, gắn với key đã dùng.

## Phần 4 — Hộp chọn giọng

- `GET /voices`: mỗi dịch vụ liệt kê bằng key đầu tiên liệt kê được (theo thứ tự Phần 3, key riêng của người đang mở). Chỉ ghi vào `problems` khi mọi key đều lỗi. Không gộp danh sách giọng từ nhiều key (trùng tên khác id). Gemini và VieNeu là danh sách cố định / catalogue nên chỉ cần "có ít nhất 1 key".
- Giới hạn đã biết, ghi trong docs: giọng ElevenLabs riêng (voice clone) của tài khoản key dự phòng không chạy được trên key chung đầu tiên; khi render rơi xuống key đó thì mới đọc được. Không xử lý thêm đợt này.

## Phần 5 — Phạm vi: lời đọc trước

- Đợt này chỉ đổi key cho **lời đọc** (3 dịch vụ trong `tts.py`), trên mọi đường `make_voices`.
- Tạo ảnh / sửa ảnh Gemini, Cloudflare, kho ảnh/clip (Pixabay/Pexels/Unsplash) và tách lời ElevenLabs (`reference.py`) dùng `source_keys.get()` = **key chung đầu tiên** (hoặc `.env`), y như hôm nay. Ghi trong báo cáo là chưa làm đa key cho các việc này.

## Phần 6 — Hạn mức theo từng key (gộp tính năng `feature/ai-service-usage`)

- **Bảng `ai_service_calls` thêm cột `api_key_id`** (nullable, FK tới bảng key mới, `ON DELETE SET NULL`). Lượt gọi bằng key `.env` hoặc từ trước migration thì NULL. Migration gắn các dòng `service = 'gemini'` cũ vào key Gemini chung đầu tiên được chuyển sang (nếu có), để số "hôm nay" không về 0 sau khi deploy.
- `service_usage.record(db, service, kind, api_key_id)`: ghi trước mỗi lần gọi, với đúng key sắp dùng. Ảnh và sửa ảnh Gemini/Cloudflare ghi theo key chung đầu tiên.
- **Thẻ trên Nguồn tư liệu hiện theo từng key chung** (ElevenLabs, Gemini; Cloudflare vẫn 1 key):
  - ElevenLabs: mỗi key một dòng — nhãn …4 ký tự, ký tự đã dùng / giới hạn, ngày làm mới (gọi `/v1/user/subscription` cho từng key; cache 5 phút theo hash key như hiện có; "Làm mới" hỏi lại mọi key).
  - Gemini: mỗi key một dòng — số lượt app gửi hôm nay (ảnh / sửa ảnh / lời đọc), giờ làm mới chung. Key `.env` một dòng riêng nếu đang dùng.
  - Một key bị nhà cung cấp báo hết hạn mức trong kỳ hiện tại thì dòng đó hiện "Đã hết lượt" (Gemini: từ lượt `kind=voice` bị từ chối hôm nay — ghi lại bằng cột `exhausted` hoặc `kind`, chọn cách ít xáo trộn, nêu trong báo cáo). Đây chỉ là hiển thị, không dùng để bỏ qua key ở job sau.
- **VieNeu**: nhánh `ai-service-usage` chưa có thẻ hạn mức VieNeu; đợt này không thêm (ngoài phạm vi), chỉ đếm lượt nếu rẻ.
- **"Key API của tôi" hiện hạn mức của chính key riêng** của người đang đăng nhập, cùng dạng dòng như trên. `GET /settings/sources/usage` không bao giờ trả hạn mức hay số lượt của key riêng người khác (key riêng không xuất hiện trên Nguồn tư liệu).
- Không làm: biểu đồ theo ngày, cảnh báo sắp hết, tự chuyển key theo số đếm.

## Mô hình dữ liệu + migration

- Bảng mới `api_keys` (tên theo lệ số nhiều của repo; nêu trong báo cáo nếu đổi): `id`, `user_id` (NULL = key chung; khác NULL = key riêng; FK `users.id` `ON DELETE CASCADE`), `service` (elevenlabs/gemini/vieneu), `encrypted_key`, `label`, `position`, `created_by_id`, `created_at`, `updated_at`. Index (`service`, `user_id`, `position`).
- Migration mới (số sau migration của `ai_service_calls`): chuyển key `elevenlabs`/`gemini`/`vieneu` trong AppSetting `source_keys` thành dòng `position = 0` của key chung; **xoá 3 tên đó khỏi AppSetting** để chỉ còn một nơi lưu (4 tên còn lại — kho ảnh, cloudflare — giữ trong AppSetting). Key đã lưu nhưng không giải mã được ("unreadable") cũng chuyển sang, giữ trạng thái "cần dán lại". Downgrade đưa key đầu tiên về AppSetting. Ghi lựa chọn này trong file quyết định.
- `source_keys.get(db, name)` **giữ nguyên chữ ký** (trả key chung đầu tiên đọc được, rồi `.env`) để mọi nơi gọi hiện có (ảnh, kho, `reference.py`, `/voices`) không đổi. Thêm hàm mới, vd `source_keys.chain(db, name, user_id) -> list[KeyRef]` (id, nhãn, đuôi 4 ký tự, nguồn, key) theo thứ tự Phần 3, chỉ `make_voices` và `/voices` dùng.
- Validation khi lưu như `save()` hiện tại, cho cả key chung và key riêng; nhãn ≤40 ký tự; tối đa ~10 key mỗi dịch vụ mỗi người (chặn dán nhầm hàng loạt).

## API + web cần đổi

- API: `routes_api_keys.py` (prefix riêng) cho key riêng: liệt kê / thêm / đổi nhãn / lên-xuống / xoá, chỉ của người đang đăng nhập (404 với key của người khác). Endpoint key chung hiện có (Nguồn tư liệu, Mô hình AI cho VieNeu) mở rộng thành danh sách. Không endpoint nào trả key đầy đủ. `GET /voices` theo Phần 4. `GET /settings/sources/usage` và endpoint hạn mức key riêng theo Phần 6.
- Web: thẻ ElevenLabs/Gemini ở Nguồn tư liệu và thẻ VieNeu ở Mô hình AI thành danh sách key; `ServiceUsage.tsx` hiện từng key; trang mới "Key API của tôi" trong nhóm "Của tôi". Chữ trên UI tiếng Việt.
- `make_voices` trong `jobs.py`: thử chuỗi key theo Phần 3, ghi log đổi key, ghi lượt theo key.

## Test (bắt buộc theo lệ team)

- Bằng fake services (base-URL env vars → `api/scripts/fake_services.py`); fake cần phân biệt được key (vd key có chữ `exhausted` → trả hết hạn mức) để test nhiều key.
- Các ca: (1) key chung Gemini đầu hết lượt ngày → dùng key chung thứ hai; (2) hết mọi key chung → dùng key riêng của chủ video; (3) hết mọi key → job lỗi với thông báo đã thử hết; (4) key riêng của A không bao giờ dùng cho video của B, kể cả khi A bấm render video của B; (5) không API nào trả key đầy đủ, `/api-keys` không trả key của người khác; (6) đúng thứ tự thử; (7) Gemini 401 / ElevenLabs 401 không kèm quota / VieNeu 401 → không đổi key; (8) **ElevenLabs 401 `quota_exceeded` → đổi key**; (9) Gemini 429 theo phút → chờ trên cùng key, không đổi; (10) key đã hết bị bỏ qua cho các cảnh sau cùng job (đếm lượt gọi fake); (11) đường "Tạo giọng thật" (`run_voice_job`) cũng đổi key; (12) setup cũ 1 key chung chạy y như trước, migration chuyển key + dòng `ai_service_calls` cũ đúng; (13) ảnh Gemini vẫn dùng key chung đầu tiên; (14) hạn mức hiện theo từng key, Nguồn tư liệu không có key riêng, "Key API của tôi" chỉ có key của mình.
- E2E: thêm/lên-xuống/xoá key chung và key riêng (theo lệ E2E chịu được CI chậm); không chạy E2E render toàn bộ ở máy.
- "Xong" = lint + typecheck pass, test cho hành vi đổi có và pass, docs cập nhật trong cùng PR.

## Tài liệu + quyết định

- Cập nhật `docs/architecture.md` (Data Model: `api_keys`, cột mới của `ai_service_calls`; Video Pipeline: chuỗi key lời đọc) và tài liệu trang Cài đặt nếu có; nêu tên file đã sửa trong báo cáo.
- File quyết định mới trong `docs/decisions/`: `2026-11-18-personal-api-keys.md` (key riêng, thay điểm "no member has keys" của 09/11; chủ video quyết định key riêng nào dùng), `2026-11-18-tts-key-fallback.md` (tín hiệu đổi key từng dịch vụ, 401 không đổi trừ ElevenLabs `quota_exceeded`; không lưu trạng thái hết hạn qua job; key ảnh = key chung đầu tiên; AppSetting bỏ 3 tên lời đọc). Gộp thành một file nếu ngắn.

## Kiểm chứng + đưa lên

- Chạy: `ruff check --fix` + `ruff format` (api + worker), `pytest` api (các test đã thêm/sửa), `npm run format && npm run lint && npm run typecheck` (web), E2E đã thêm/sửa. Nêu kết quả thật từng lệnh trong báo cáo 3 phần.
- Không tự merge. PR có `Closes #<số>` nếu có issue; CI xanh mới được merge.
- Không chạm render core hay mẫu video → không cần người xem MP4 mẫu. Nếu lúc làm chạm render core thì dừng và báo user.

## Ngoài phạm vi

- Đa key cho tạo ảnh / sửa ảnh / kho ảnh / tách lời ElevenLabs (Phần 5).
- Thẻ hạn mức VieNeu, biểu đồ, cảnh báo sắp hết, tự mua/nạp credits.
- Gộp danh sách giọng từ nhiều tài khoản ElevenLabs.
- Đổi giới hạn của nhà cung cấp — chỉ bật thanh toán bên Google/ElevenLabs mới đổi được.

## Câu hỏi cần chốt

1. ~~Owner đồng ý đảo điểm "no member has keys of their own" của quyết định 09/11?~~ Đã đồng ý (18/11/2026); ghi lại trong `2026-11-18-personal-api-keys.md`.
2. ~~Đồng đội render video của U thì dùng key riêng của ai?~~ Đã chốt (18/11/2026): video của người nào thì render bằng key riêng của người đó (chủ video = `created_by_id`), bất kể ai bấm render.
3. ~~Video do job hệ thống tạo lấy key của ai?~~ Đã rõ trong code: mọi video có `created_by_id` NOT NULL → dùng chủ video.
4. ~~Đổi key khi 401?~~ Không, trừ ElevenLabs 401 kèm `quota_exceeded` (đó là hết ký tự, không phải key sai).
5. ~~Ai sửa key chung?~~ Mọi thành viên, như hiện tại, có ghi Lịch sử.
