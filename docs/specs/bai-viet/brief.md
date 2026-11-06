# Brief: Bài viết — đăng bài post ảnh/chữ lên Page

Dành cho Claude Code. Đọc AGENTS.md trước khi sửa. Không commit/merge. Không đụng production. Test bằng fake service, không gọi API thật. Chạy pytest hiện có trước khi sửa — nếu đã đỏ thì dừng và báo. Báo cáo 3 phần: Done / Verified (lệnh thật đã chạy) / Remaining risks.

## 0. Bối cảnh và quyết định

### 0.1 Đã chốt

- App hiện chỉ làm và đăng reel. Tính năng mới là mục riêng **Bài viết** (tên đã chốt 2026-11-05), tách khỏi Video: mục riêng ngang hàng trong sidebar, không nhét vào màn Video.
- Vai trò: bài viết KHÔNG thay reel. Việc của nó là test chủ đề rẻ (bài nào thắng mới làm reel), giữ page đều, gom bình luận làm nguồn insight cho ngân hàng chủ đề.
- Các luật sau áp nguyên từ reel, không viết lại: tiền riêng theo người (link affiliate là của chủ Page, `Fanpage.owner_id` + `shopee_account_id`); không bao giờ đăng cùng nội dung lên nhiều page; từ cấm của topic + disclaimer "Tham khảo, không thay thế tư vấn bác sĩ" áp cho caption; link affiliate chỉ trong bình luận ghim, không trong caption; không tạo cờ "bài thắng" dưới bất cứ tên nào — chỉ tô đậm lúc hiển thị khi reach ≥ 10× trung vị; đo 48h, không dùng số mới nhất thay số 48h; bài đã xoá/huỷ không vào trung vị, KPI hay tổng (decisions 2026-11-06); một bài không bao giờ được đăng hai lần (decisions 2026-10-31).
- Dạng bài là danh sách cố định (lưu dạng chuỗi): `kien_thuc` (kiến thức ngắn), `meo` (mẹo vặt), `cau_hoi` (câu hỏi/thăm dò), `canh_bao` (cảnh báo/nhắc nhở), `tra_loi_binh_luan` (trả lời bình luận bằng bài viết), `checklist` (tổng hợp/danh sách). Không thêm dạng mới khi chưa duyệt.

### 0.2 Chủ sản phẩm chốt TRƯỚC khi giao việc

Hai điểm dưới đây đụng quyết định đã ghi trong `docs/decisions.md`. Agent không tự chọn: nếu mục này chưa được điền thì dừng và hỏi.

1. **Mở lại đăng bài ảnh/chữ.** Entry 2026-11-03 ("Bình luận" answers visitors as the Page…) ghi: photo and text posts (`pages_manage_posts`) wait, vì rủi ro "unoriginal content" với ảnh stock. Brief này đảo quyết định đó. Đề xuất giảm rủi ro: trong MVP bài viết **không dùng ảnh stock**; ảnh chỉ là Thẻ chữ, ảnh AI, ảnh dán link (thành viên chịu trách nhiệm như clip TikTok, 2026-11-03), hoặc không ảnh. → Chốt (2026-11-06): ☑ đồng ý đề xuất — không dùng ảnh stock.
2. **Từ cấm trong caption: cảnh báo hay chặn?** Entry 2026-10-31 "Banned words warn, they never block the render". Mặc định đề xuất: **giữ cảnh báo vàng, không chặn** (giống reel), hiện cảnh báo ngay trên nút Đăng. → Chốt (2026-11-06): ☑ chỉ cảnh báo (link trong caption vẫn chặn đăng).

Cả hai được ghi thành entry mới trong `docs/decisions.md` ở PR đầu tiên (mới nhất lên đầu, nói rõ entry nào bị thay đổi).

### 0.3 Điều kiện bắt đầu code

- Phase 0 (§3) đạt tiêu chí đi tiếp.
- App Meta "ALSK Page Manager" đã chuyển sang **Live** (decisions 2026-11-06). Khi app còn Development mode, bài đăng qua API chỉ người có vai trò trong app thấy được, nên reach đo được không có nghĩa.

## 1. Luồng người dùng

1. Vào mục Bài viết → "Tạo bài viết" → chọn nhóm chủ đề + dạng bài.
2. Soạn caption: tự gõ, hoặc nhờ AI viết rồi sửa. Dạng `cau_hoi` không cần ảnh.
3. Chọn ảnh (không bắt buộc, nguồn theo chốt ở §0.2.1): ảnh AI, dán link, hoặc "Thẻ chữ": nền màu + chữ hook vẽ bằng Pillow (§2.3). Không ảnh cũng là trạng thái hợp lệ, không báo lỗi.
4. Gắn tối đa 2 sản phẩm affiliate đã duyệt (luật duyệt sẵn). Khi có gắn sản phẩm, caption được kết bằng đúng 1 câu "Link sản phẩm mình để ở bình luận ghim" — trỏ sang bình luận, không nhét link vào caption.
5. Chọn Page đích lúc đăng (như video). Đăng ngay hoặc lên lịch; nếu giờ chọn nằm trong khoảng ±2 giờ của một reel đã lên lịch cùng Page thì cảnh báo. Bài viết KHÔNG vào hàng chờ của Page (decisions 2026-11-05) trong MVP.
6. Đăng xong: trạng thái đã đăng + link bài. Worker tự viết bình luận chứa link affiliate dưới bài (§2.4); thành viên ghim tay.
7. Đo ở mốc 48h (§2.5). Bài thắng → nút "Làm reel từ bài này" tạo video nháp với chủ đề của bài.
8. Gỡ bài: nút "Gỡ bài" xoá bài khỏi Facebook (§2.7).

## 2. Luồng hệ thống

### 2.0 Tên trong code — KHÔNG dùng "post"

`routes_posts.py` (`/api/posts`) và trang web `/posts` ("Bài đăng") đã tồn tại và nghĩa là **Publication**; bảng `post_metrics` cũng là số của Publication. Để "post" không mang hai nghĩa, bài viết dùng tên **article** ở mọi chỗ trong code:

- Bảng `articles`, model `Article`, `routes_articles.py` (prefix `/api/articles`), trang web `web/src/app/(app)/articles/`, cột FK `article_id`, job kind `article_caption`.
- Chữ hiển thị cho người dùng vẫn là "Bài viết".

### 2.1 Model — migration mới (số tiếp theo trong `api/migrations/versions`, hiện mới nhất là 0044; kiểm tra lại lúc làm, không đoán)

- Bảng `articles`: id, knowledge_topic_id (FK), kind (String, 1 trong 6 dạng), caption (Text), hashtags (JSONB, tối đa 5), image_key (nullable), image_kind (`ai` | `link` | `text_card` | `stock` nếu §0.2.1 cho phép | null), source_comment_id (nullable, FK `page_comments.id`, chỉ cho `tra_loi_binh_luan`), created_by_id, created_at, updated_at. Trạng thái đăng KHÔNG lưu trên article mà đọc từ Publication của nó (như video).
- `knowledge_topics.article_prompt` (Text, mặc định "") + file mặc định `prompts/article_default.txt`.
- `jobs.article_id` (nullable, FK `articles.id`) + partial unique index `uq_jobs_active_article` (chỉ 1 job active cho 1 article), theo mẫu `uq_jobs_active_video`. Thêm kind `article_caption` vào `JOB_KINDS` ([videos.py](../../../api/src/reels_api/videos.py)), không đổi kind cũ. Đăng và gỡ dùng lại kind `publish`/`unpublish` (§2.4, §2.7), không thêm `post_publish`.
- `publications.video_id` thành nullable + thêm `article_id` (nullable, FK `articles.id`) + CheckConstraint "đúng một trong hai có giá trị". Index `uq_publications_pending` giữ cho video và thêm partial unique index mới `(article_id, platform) WHERE status='pending'`. Thêm cột cần cho chống đăng hai lần (§2.4), ví dụ `publish_sent_at`, nếu `finish_sent_at` không dùng lại được.
- `article_affiliate_products` (article_id, product_id, khoá chính kép) — tương tự `video_affiliate_products`.
- `affiliate_links`: `video_id` thành nullable + thêm `article_id` (nullable) + CheckConstraint "đúng một trong hai". Unique `uq_affiliate_links_target` hiện là `(product_id, account_id, video_id, fanpage_id)`; vì NULL không trùng nhau trong Postgres, thay bằng 2 partial unique index: một cho video (`WHERE video_id IS NOT NULL`), một `(product_id, account_id, article_id, fanpage_id) WHERE article_id IS NOT NULL`. subId cho bài viết: [`bv{article_id}`, `p{fanpage_id}`] (video hiện là [`v{video_id}`, `p{fanpage_id}`], `affiliate.sub_ids`).
- Không thêm bảng hay cột số liệu — tái dùng `post_metrics` (gắn với Publication), xem §2.5.
- Migration đổi constraint trên `publications` và `affiliate_links` (bảng có dữ liệu thật): viết cả downgrade, test upgrade trên DB có sẵn dữ liệu video, ghi rõ trong PR để người review đọc kỹ.

### 2.2 Viết caption — job `article_caption`

- Gọi `llm.complete` như job script. `claude._assemble` hiện luôn gắn `OUTPUT_FORMAT` JSON của video và câu từ cấm nói về "tiêu đề, chữ trên màn hình, lời đọc…". Thêm tham số (ví dụ `output_format` và cách diễn đạt câu từ cấm) cho `_assemble` để bài viết dùng chung đúng một hàm lắp ráp — KHÔNG viết hàm lắp ráp thứ hai, và không đổi kết quả của video (test cũ phải giữ nguyên).
- OUTPUT_FORMAT cố định cho bài viết (code, không phải prompt — "Prompt text is app data, the output format is code"): hook 1 dòng; nội dung 3–5 dòng; kết bằng 1 câu hỏi; disclaimer 1 dòng "Tham khảo, không thay thế tư vấn bác sĩ"; hashtags tối đa 5, đặt cuối; không link; không bịa lời chứng khỏi bệnh. Dạng `cau_hoi`: chỉ hook + câu hỏi. Dạng `tra_loi_binh_luan`: mở đầu bằng việc nhắc lại bình luận gốc (lấy từ `source_comment_id`, rào trong prompt là lời người xem, như ghi chú ở job `revise`).
- Từ cấm: theo chốt §0.2.2. Kiểm tra cả caption tự gõ, không chỉ caption AI. Caption chứa link (http, shope.ee, …) thì chặn hẳn: đây là luật đã chốt "link chỉ trong bình luận", không phải từ cấm.

### 2.3 Ảnh

- Tái dùng ảnh AI (`imagegen`) và dán link (`remote_media`); ảnh stock chỉ khi §0.2.1 cho phép. Không viết đường lấy ảnh mới.
- "Thẻ chữ" (MVP): Pillow vẽ nền màu + chữ hook (dòng đầu caption). Pillow đã có trong api (`clips.py`). Kiểm tra font hỗ trợ tiếng Việt trên server; nếu thiếu thì kèm font vào repo (giấy phép mở, ghi trong báo cáo) thay vì dùng font không dấu.
- `image_key` null là hợp lệ (bài chỉ chữ). Màn soạn không báo lỗi khi chưa có ảnh.

### 2.4 Đăng — job `publish` mở rộng + `facebook.py`

- Code hiện chỉ đăng reel (`/{page-id}/video_reels`). Thêm hàm đăng bài ảnh (`/{page-id}/photos`, ảnh + caption) và bài chỉ chữ (`/{page-id}/feed`), kèm `published=false` + `scheduled_publish_time` khi lên lịch. Tái dùng `Publication.scheduled_at`, trạng thái `scheduled`/`published`, job `check` sau giờ hẹn.
- Job `publish` đọc Publication pending: có `video_id` thì đi đường reel cũ (không đổi), có `article_id` thì đi đường bài viết.
- **Không bao giờ đăng hai lần** (decisions 2026-10-31): ghi mốc "đã gửi yêu cầu đăng" vào Publication TRƯỚC khi gọi Facebook, lưu id bài ngay khi có. Thử lại khi mốc đã có mà chưa có id: tìm trên Page bài có cùng caption trong khoảng thời gian đó trước khi gửi lại; không tìm được chắc chắn thì chờ thành viên, không tự gửi.
- Quyền token: token Page đã có `pages_manage_posts` (theo `docs/facebook-app-visibility-guide.md`). Vẫn xử lý lỗi thiếu quyền bằng thông báo tiếng Việt như `read_insights`; không đổi scope token trong code.
- Bình luận affiliate: cơ chế hiện tại ([post_comments.py](../../../api/src/reels_api/post_comments.py) gọi `affiliate.comment_text`, đọc sản phẩm qua `video_affiliate_products` và tạo link theo `post.video_id`). Mở rộng để Publication có `article_id` đọc `article_affiliate_products` và link `affiliate_links.article_id`; giữ nguyên luật "không bao giờ hai bình luận" và "không phải job". Kiểm tra endpoint `/{object-id}/comments` với id bài photo/feed trên fake service.
- Quy tắc: Page chọn lúc đăng; link affiliate không bao giờ vào caption; trùng nội dung chặn theo §2.6.

### 2.5 Đo 48h — mở rộng `measure_due` và `analytics`

- Mở rộng `measure_due` ([metrics.py](../../../api/src/reels_api/metrics.py)) cho Publication có `article_id`: reactions/bình luận/chia sẻ/reach, lưu vào `post_metrics` với `views` NULL, `reach` làm số chính, `plays`/`replays`/`retention` NULL. Cửa sổ `latest`/`48h` giữ nguyên nghĩa: `48h` là lần đọc đầu tiên từ 48h sau `published_at`, không viết lại.
- **Tên metric reach của bài Page:** `post_impressions_unique` đã bị Meta khai tử (6/2026). Trước khi viết code, tìm tên thay thế trong tài liệu Meta hiện hành (Context7 hoặc trang Graph API) và ghi nguồn vào PR. Nếu không xác định được thì vẫn làm, để reach NULL, hiện "Facebook không trả reach" và ghi vào Remaining risks — không đoán tên. Tên metric tập trung một chỗ trong `facebook.py`, hỏi từng metric riêng khi Meta trả lỗi #100 (như `reel_insights`).
- KPI: share/reach ≥ 0,2% (tái dùng `analytics.SHARE_GOAL`, không hardcode ở frontend). Trung vị reach riêng từng Page, chỉ trên bài viết (không trộn reel), 60 ngày như reel, tối thiểu `MIN_SAMPLES` (5). Bài `deleted`/`cancelled` không vào trung vị/KPI/tổng. **Bình luận là tín hiệu chính khi reach còn nhỏ; share/reach chỉ xét khi reach ≥ 50.** Hiển thị: "{reactions} cảm xúc · {comments} bình luận · {shares} chia sẻ · reach {reach} · share/reach {rate}%"; chưa đủ mẫu → "chưa đủ dữ liệu (cần ≥5 bài đã đo 48h)"; chưa đo 48h → "chưa đo 48h".
- Không tạo cờ "bài thắng". Chỉ tô đậm lúc hiển thị khi reach ≥ 10× trung vị Page.

### 2.6 Chống trùng nội dung

- Trước khi đăng: hash caption đã chuẩn hoá (bỏ dấu, lowercase, gọn khoảng trắng, bỏ hashtag) so với các bài viết đã có Publication `scheduled`/`published`. Đã có ở Page khác → cảnh báo, chờ xác nhận; cùng Page → chặn hẳn.

### 2.7 Gỡ bài — job `unpublish` mở rộng

- Giữ `publication_id` làm đầu vào của job `unpublish`. Publication có `article_id` thì gọi `DELETE /{post-id}`; trạng thái chuyển `deleted` như reel. Áp luật nhận biết bài đã bị xoá trên Facebook (400 #100 khi token vẫn đọc được Page, decisions 2026-11-06) cho cả bài viết.

### 2.8 Web

- Nav "Bài viết" (`/articles`), mục riêng ngang hàng "Video" trong `NAV` của `AppShell.tsx`.
- "Bài đăng" (`/posts`) hiện là danh sách Publication **gom theo video** (decisions 2026-11-03). MVP: KHÔNG đưa bài viết vào đó; số liệu và trạng thái đăng của bài viết nằm trên trang "Bài viết". Gộp chung với bộ lọc Reel/Bài viết là việc sau, cần quyết định riêng.
- Trang danh sách: trạng thái, Page, chủ đề, dạng bài, số 48h (§2.5).
- Màn soạn: chủ đề + dạng bài, caption (AI viết / tự gõ), ảnh (theo §2.3 / không ảnh), gắn sản phẩm (tối đa 2), chọn Page lúc đăng, đăng ngay / lên lịch, xem trước dạng thẻ Facebook (ảnh + caption + tên Page, thấy rõ link KHÔNG nằm trong caption). Form mở trong drawer (decisions 2026-11-03).
- Nút "Làm reel từ bài này" (tối giản): tạo video nháp với chủ đề của bài, tái dùng luồng "Tạo video".

## 3. Thứ tự làm

- **Phase 0 (không code):** test tay 2 tuần trên Ăn Lành — 3 bài, 1 bài mỗi dạng (kiến thức, mẹo, câu hỏi), đăng tay trong Meta Business Suite ở khung giờ không phải giờ vàng của reel, đo 48h. Tiêu chí chốt TRƯỚC khi test: làm tiếp nếu có ≥1 bài đạt share/reach ≥ 0,2% với reach ≥ 50, hoặc tổng bình luận 3 bài ≥ 10; dừng nếu cả 3 bài gần như 0 tương tác. (Ngưỡng là ví dụ, chủ sản phẩm chỉnh trước khi test.)
- **Phase 1 (MVP), 3 PR nối tiếp, mỗi PR một nhánh, PR sau bắt đầu khi PR trước đã merge:**
  1. **Soạn bài:** migration + model + `routes_articles.py` (CRUD) + job `article_caption` + Thẻ chữ + trang danh sách và màn soạn (chưa có nút Đăng) + entry decisions §0.2. Đã làm (nhánh `feature/bai-viet`); migration chỉ có `articles`, `knowledge_topics.article_prompt`, `jobs.article_id`. Ảnh AI cho bài viết chưa làm (cần job ảnh riêng), dời sang PR 2.
  2. **Đăng:** `facebook.py` (đăng ảnh/chữ, gỡ) + mở rộng `publish`/`unpublish`/`check` + bình luận affiliate + chống trùng + nút Đăng/Gỡ trên web. Đã làm cùng nhánh `feature/bai-viet` (migration 0046). Ảnh AI vẫn chưa làm.
  3. **Đo và làm reel:** mở rộng `measure_due` + analytics + số 48h trên web + nút "Làm reel từ bài này" + entry decisions §4. Đã làm cùng nhánh; reach là `post_total_media_view_unique` (changelog Graph API v25).
- **Phase 2:** bản đầy đủ "làm reel từ bài thắng" (chuyển caption thành nháp kịch bản), tuỳ biến thẻ chữ, bài viết trong "Bài đăng" và hàng chờ Page, xem trước đúng giao diện feed.
- **Không làm:** carousel nhiều ảnh; đăng cùng nội dung lên nhiều page; post TikTok/YouTube; tự động ghim bình luận; đổi cách reel hoạt động; cờ "bài thắng"; dùng số mới nhất thay số 48h.

## 4. Kiểm chứng

- Chạy pytest hiện có về publish/metrics/affiliate TRƯỚC khi sửa — nếu đã đỏ thì dừng và báo.
- Test mới (fake service, không gọi API thật): tạo bài + viết caption (từ cấm báo đúng, link trong caption bị chặn, video vẫn lắp prompt như cũ); migration lên/xuống trên DB có sẵn video và publication; đăng bài ảnh + bài chỉ chữ + lên lịch; thử lại sau khi mất câu trả lời không tạo bài thứ hai; bình luận affiliate dưới bài viết; đo 48h (views NULL, reach số chính, share/reach chỉ xét khi reach ≥ 50, bài đã xoá không vào trung vị); chống trùng (khác Page cảnh báo, cùng Page chặn); gỡ bài; làm reel từ bài.
- `api/scripts/fake_services.py` thêm endpoint `/{page-id}/photos`, `/{page-id}/feed`, insights của bài và DELETE bài, trả lời giống Facebook.
- Web: format + lint + typecheck; E2E tạo → đăng (fake) → gỡ trên màn Bài viết, chạy local trước khi push.
- `docs/decisions.md` (mới nhất lên đầu, không sửa entry cũ): §0.2 ở PR 1; ở PR 3 ghi quyết định tái dùng Publication/PostMetrics cho bài viết thay vì bảng đăng riêng, và KPI share/reach với ngưỡng reach ≥ 50. Cập nhật `docs/architecture.md` (Data Model) và `docs/project.md` trong PR tương ứng.

## 5. Hàng đợi và lệnh giao việc

- Brief này xếp hàng sau đợt plan-tab và sau spec dán nhiều link. Không làm song song với 2 việc trên trên cùng working tree.
- Model: PR 1 và PR 2 đụng migration đổi constraint trên bảng có dữ liệu thật và luật chống đăng hai lần — dùng Opus (hoặc Sonnet effort high) và người review đọc kỹ migration. PR 3 dùng Sonnet effort medium được. Không dùng subagent.
- Lệnh giao Claude Code (mỗi PR một lần): "Đọc và làm theo brief trong docs/specs/bai-viet/brief.md, chỉ phần PR <số> ở §3, theo đúng thứ tự trong đó. Nếu §0.2 chưa được chốt thì dừng và hỏi. Đọc AGENTS.md trước khi sửa, không commit/merge, báo cáo 3 phần Done / Verified (lệnh thật đã chạy) / Remaining risks."
