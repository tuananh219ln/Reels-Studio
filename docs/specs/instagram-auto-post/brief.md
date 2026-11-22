# Brief: Tự động đăng Instagram theo Facebook (công tắc theo Page)

## 0. Bàn giao

- Model: Sonnet, effort medium, KHÔNG dùng subagent. Đọc `AGENTS.md` trước khi sửa; agent sửa file trên nhánh `feature/instagram-auto-post` rồi dừng ở working tree, không commit/merge (người mở PR); không đụng production; test chỉ qua fake services, không gọi Instagram/Facebook thật.
- Làm theo đúng thứ tự §8 (bỏ bước 0 nếu brief ghi vậy). Chạy pytest liên quan sau mỗi bước; bước nào đỏ thì dừng và báo.
- Báo cáo 3 phần khi xong: Done / Verified (lệnh thật đã chạy) / Remaining risks.
- Brief này đảo 1 quyết định cũ: §5 của `docs/specs/instagram-posting/brief.md` ("Không đưa Instagram vào hàng chờ Page hay tự đăng theo khung giờ Facebook như TikTok auto-post") — ghi vào file quyết định mới `docs/decisions/2026-11-22-instagram-auto-post.md` (cùng PR), nêu rõ chỗ đảo.
- Phạm vi đợt đầu: chỉ Page Tiệm Đọc Comment (user chốt tối 22/11/2026, xem §1).

## 1. Vấn đề

- Đăng Instagram đã có sẵn trên tool (brief `docs/specs/instagram-posting/brief.md`, theo yêu cầu tuananh219ln 19/11): bảng "Đăng bài" có 4 ô tick, một lần bấm đăng lên N nền tảng, hẹn giờ được như Facebook. Nhưng mỗi video vẫn phải tick Instagram bằng tay.
- TikTok thì đã tự động theo Page (`tiktok_auto_mode` + `jobs.queue_tiktok_posts`): video lên Facebook đúng giờ là tự có bài TikTok. Instagram chưa có đường tự động tương đương — brief IG §5 cố tình loại trừ.
- Người dùng (Truong) hỏi tối 22/11/2026: "Đăng fb có tự đăng ig ko" — câu trả lời hiện tại là không. Đã thử đăng tay 1 video qua API Instagram ngoài tool (video 310, 113,2 giây, lên @tiemdoccomment lúc 18:22 cùng ngày, link https://www.instagram.com/reel/DgCr3wsD_Ob/) — chạy được, Instagram nhận reel dài hơn 90 giây. Sau bài thử, user chốt hướng **code thẳng vào tool** (không dùng job ngoài, không đăng tay lâu dài).

Mục tiêu: chủ Page bật một công tắc trên Page, từ đó mọi video hẹn giờ lên Facebook của Page đó tự đăng kèm lên Instagram đã liên kết, cùng khung giờ.

## 2. Quyết định (ghi vào file quyết định mới)

1. **Đi theo đúng mẫu TikTok auto, không móc vào route đăng Facebook.** Một vòng quét trong worker (`jobs.queue_instagram_auto_posts`, gọi trong `worker.py queue_checks()` cạnh `queue_tiktok_posts`) đọc các bài Facebook đã tới giờ và tạo bài Instagram. Lý do: vòng quét bắt được mọi đường hẹn giờ (bảng "Đăng bài", hàng chờ Page, job hẹn qua trình duyệt, MCP `schedule_video`), còn móc vào route đăng thì sót đường hàng chờ.
2. **Công tắc theo Page, mặc định TẮT cho mọi Page** (`Fanpage.instagram_auto`, bool). Instagram không có chế độ nháp như TikTok nên công tắc chỉ là bật/tắt, không phải mode. Page chưa liên kết Instagram thì không bật được.
3. **Giờ đăng Instagram = sau giờ Facebook khoảng 1 phút**, không phải đúng từng phút. Instagram API không có hẹn giờ; vòng quét (60 giây một lần) chính là đồng hồ — giống hệt `queue_instagram_posts` đang làm cho bài Instagram hẹn tay.
4. **Chỉ bài Facebook HẸN GIỜ mới kích hoạt auto; bài "Đăng ngay" thì không** — giống TikTok auto. Bài đăng ngay do thành viên tự bấm, họ tick Instagram trong bảng "Đăng bài" khi cần.
5. **Cửa sổ quét 24 giờ** như `TIKTOK_SWEEP_WINDOW`: bài Facebook quá 24 giờ không được gửi bù, để bật công tắc muộn không gây lũ bài cũ.
6. **Không thêm quyền, token, hay kết nối mới.** Đăng IG dùng token Page đã lưu và tài khoản `instagram_user_id` đã đọc ở mỗi lần kiểm tra Page (migration 0111/0112). Không đọc số liệu, không bình luận Instagram trong đợt này.
7. **Bài Instagram lỗi không tự đăng lại.** Vòng quét bỏ qua video đã có bài Instagram ở BẤT KỲ trạng thái nào trừ `cancelled` (kể cả `failed`); thành viên bấm "Thử lại" như bài hẹn tay. Nếu không, lỗi lặp lại (vd. token thiếu quyền) sẽ tạo bài + Job mới mỗi 60 giây trong 24 giờ. Chủ ý khác TikTok auto ở điểm này.
8. **Chống trùng không lọc theo Page**: hai Page cùng bật auto với hai tài khoản Instagram khác nhau thì chỉ Page nào được quét trước đăng (một MP4 lên một tài khoản Instagram một lần, như quyết định 2026-11-19). Caption lấy từ `video.caption` như route tay, nên có thể lệch nếu thành viên sửa nội dung lúc đăng Facebook.
9. **Đợt đầu chỉ bật cho Page Tiệm Đọc Comment.** Page Tôi Đọc Threads chưa có Instagram liên kết nên chưa bật được; các Page khác (Ăn Lành, Già, Ăn Ngon Mỗi Ngày) giữ tắt cho tới khi user quyết riêng từng Page.

## 3. Sự thật đã kiểm chứng trên main (SHA 0714da05 — kiểm chứng 22/11/2026, kiểm tra lại tối cùng ngày: main vẫn đúng SHA này, chưa có commit mới)

- Client Instagram (`api/src/reels_api/instagram.py`): Facebook Login, token Page, `POST /{ig-user-id}/media` với `media_type=REELS`, `upload_type=resumable`, `caption`, `share_to_feed=true`; upload MP4 lên `rupload.facebook.com` (env `INSTAGRAM_UPLOAD_URL`); poll `status_code` tới `FINISHED`; `POST /{ig-user-id}/media_publish`; caption cắt 2.200 ký tự / tối đa 30 hashtag (`instagram.caption`). Lỗi thiếu quyền → "Token Page chưa có quyền đăng Instagram, hãy dán lại token có instagram_content_publish".
- Worker (`api/src/reels_api/ig_publish.py`, job kind `ig_publish`): nạp MP4 theo `remote_mp4_key`; tạo container, **lưu `remote_id` và commit NGAY** rồi mới upload; poll ~5 giây/lần tối đa ~5 phút; `FINISHED` → đặt `finish_sent_at`, commit, `media_publish` → `external_id` = media id, `post_url` = permalink, `status="published"`. Thử lại: có `remote_id` thì hỏi `status_code` trước; `PUBLISHED` thì tìm media qua `recent_media` (khớp caption, sau `finish_sent_at`).
- Route tay (`api/src/reels_api/routes_instagram.py`): `POST /api/instagram/videos/{video_id}/publish` (body `{fanpage_id, scheduled_at: datetime | null}`) tạo `Publication(platform="instagram", status="scheduled"|"pending", post_text=instagram.caption(hashtags.post_text(video.caption, video.hashtags)), remote_mp4_key=video.mp4_key)`; có giờ thì không Job, không giờ thì Job `ig_publish` ngay. `POST /api/instagram/posts/{id}/cancel` hủy bài `scheduled`.
- Vòng hẹn giờ (`jobs.queue_instagram_posts`, gọi trong `worker.py queue_checks()` mỗi 60 giây): bài `instagram` `scheduled` có `scheduled_at <= now` → `pending` + Job `ig_publish`; trễ hơn 24 giờ (`INSTAGRAM_LATE_LIMIT`) thì `cancelled` kèm Job lỗi giải thích.
- TikTok auto (`jobs.queue_tiktok_posts`, `TIKTOK_SWEEP_WINDOW = timedelta(hours=24)`): quét `Publication` Facebook `status in ("scheduled", "published")`, `scheduled_at <= now()`, `scheduled_at >= now() - 24h`; với mỗi bài: video còn `mp4_key`, Page có `owner_id` và `tiktok_account_id` (tài khoản active, đúng chủ Page), video không có job đang chạy, chưa có `Publication` TikTok nào của video ở `pending`/`scheduled`/`published`; tạo `Publication(platform="tiktok", status="pending", publish_mode=mode, ...)` + Job `tiktok_publish` trong `db.begin_nested()`, `IntegrityError` thì bỏ qua.
- Công tắc TikTok (`routes_fanpages.py`): `PUT /api/fanpages/{fanpage_id}/tiktok-auto-mode`, body `{"mode": "draft" | "direct"}`, chỉ chủ Page; `_rows` trả `tiktok_auto_mode` và `instagram: {id, username} | null` + `instagram_error`.
- Migration mới nhất trên main là `0116_affiliate_product_per_member.py` → migration đợt này là **0117**.
- Job kind là String 16; `ig_publish` vừa (10 ký tự).
- **Giới hạn độ dài Reel — ĐÃ CÓ ĐÁP ÁN (tối 22/11/2026): Instagram API nhận reel 113,2 giây.** Bằng chứng live ngoài tool: video 310 của Tiệm (113,2s) đăng tay qua Instagram Graph API lên @tiemdoccomment lúc 18:22 ngày 22/11, link https://www.instagram.com/reel/DgCr3wsD_Ob/ — bài đầu tiên của tài khoản, public, caption + 7 hashtag lấy nguyên từ Reels Studio. Code IG trong tool không chặn độ dài, nên **vòng quét KHÔNG lọc theo độ dài**. Việc còn lại chỉ là chạy 1 video dài hơn 90 giây qua đường `ig_publish` của tool ở staging (fake service) để xác nhận upload resumable + poll + publish xử lý được (§8 bước 0) — không bịa giới hạn từ trí nhớ, không gắn giới hạn 90 giây vào code.
- Bằng chứng luồng ngoài tool (22/11 18:20–18:23): MP4 video 310 tải qua trình duyệt (nút Tải MP4 trên trang video) vì token MCP bị 401 ở endpoint file — việc này KHÔNG liên quan code trong tool: worker nạp MP4 theo `remote_mp4_key` trên server, không cần tải file về. Sau khi đăng, link Instagram đã ghi vào video 310 trong tool dưới dạng "Đã đăng tay" (trang video hiện "Đã đăng: Facebook, Instagram", 2/2 nền tảng).
- **Tình trạng token Instagram của Page Tiệm (kiểm chứng 22/11 17:53, vẫn đúng tối 22/11): tool hiện Page Tiệm "Chưa liên kết Instagram"; token Page thiếu quyền `instagram_basic` + `instagram_content_publish`; khi tạo token mới cho app 'Reels Report Tool', danh sách quyền không có 2 quyền IG này — Facebook báo quản trị viên app cần thêm use case Instagram cho app. Ở cấp Meta, Page–IG vẫn liên kết (Business Suite hiện nút "Đi đến Instagram") — thiếu chỉ là quyền IG trong token và việc chỉ định IG cho System User.** Công tắc auto KHÔNG bật được cho Tiệm cho tới khi xong việc token này (xem §7 bước 0).

## 4. Thiết kế

### 4.1 Dữ liệu (migration 0117 trong `api/migrations/versions`)

- `fanpages`: thêm `instagram_auto` (Boolean, default False, server_default false()). Comment theo mẫu `tiktok_auto_mode`: công tắc tự đăng Instagram khi video của Page lên Facebook hẹn giờ.

### 4.2 Vòng quét (`jobs.queue_instagram_auto_posts`, theo mẫu `queue_tiktok_posts`)

- Quét `Publication` Facebook `status in ("scheduled", "published")`, `scheduled_at <= now()`, `scheduled_at >= now() - TIKTOK_SWEEP_WINDOW` (dùng chung hằng số, không tạo hằng mới). Chỉ bài `video_id IS NOT NULL`.
- Với mỗi bài, bỏ qua khi: video không còn hoặc không có `mp4_key`; Page không còn, không có `owner_id`, `instagram_auto` tắt, hoặc không có `instagram_user_id`; video đang có job (`active_job`); đã có `Publication` Instagram nào của video ở trạng thái khác `cancelled` (`pending`/`scheduled`/`published`/`failed`; không lọc theo Page). Khác TikTok: `failed` cũng chặn, để lỗi không lặp mỗi phút (quyết định 7).
- Tạo trong `db.begin_nested()` (lỗi `IntegrityError` thì bỏ qua, vòng sau thử lại):
  - `Publication(video_id, platform="instagram", status="pending", fanpage_id=page.id, created_by_id=page.owner_id, remote_mp4_key=video.mp4_key, post_text=instagram.caption(hashtags.post_text(video.caption, video.hashtags)))` — caption chụp đúng như route tay, để "Thử lại" gửi đúng bản và câu trả lời mất được tìm lại bằng caption.
  - `Job(video_id, kind="ig_publish", status="queued", created_by_id=page.owner_id, publication_id=made.id)`.
  - `scheduled_at` của bài Instagram để `None` (đăng ngay khi Job chạy — vòng quét đã là đồng hồ).
- Bài "Đăng ngay" có `scheduled_at` null (`routes_videos.py`), hàng chờ Page thì gán `scheduled_at` (`page_queue.py`) nên vòng quét bắt đúng.
- Không tạo Job khi bài Facebook chỉ mới `scheduled` mà chưa tới giờ (điều kiện `scheduled_at <= now()` đã chặn). Không đụng bài Facebook.

### 4.3 Worker (`worker.py queue_checks`)

- Gọi `queue_instagram_auto_posts(db)` trong `queue_checks()` cạnh `queue_tiktok_posts(db)` (mỗi 60 giây). Không gọi trong vòng metrics (5 giây) — quét 60 giây là đủ và khớp TikTok auto.

### 4.4 Route công tắc (`routes_fanpages.py`, theo mẫu `set_tiktok_auto_mode`)

- `PUT /api/fanpages/{fanpage_id}/instagram-auto`, body `{"auto": bool}`. Chỉ chủ Page (`ensure_owner` như `set_active`); Page chưa liên kết Instagram (`instagram_user_id` null) thì 422 "Page chưa liên kết tài khoản Instagram, hãy liên kết rồi bật lại". Trả `_rows` như các route Page khác.
- `_rows`: thêm `"instagram_auto": row.instagram_auto` cạnh `"tiktok_auto_mode"`.

### 4.5 Web (theo mẫu chỗ chỉnh `tiktok_auto_mode`)

- Tìm chỗ web gọi `PUT /fanpages/{id}/tiktok-auto-mode` (OwnerLine / trang dashboard của Page) và đặt công tắc Instagram ngay cạnh: bật/tắt, chỉ chủ Page thấy; Page chưa liên kết Instagram thì công tắc tắt mờ kèm chữ "Chưa liên kết Instagram" (dùng `row.instagram` đã có trong `_rows`).
- Type `Fanpage` trong `web/src/lib/api.ts`: thêm `instagram_auto: boolean`.
- Không sửa bảng "Đăng bài" — bài auto tạo ra hiện như bài Instagram hẹn tay đã có (link, Hủy hẹn, trạng thái).

## 5. Không làm

- Không móc vào `routes_videos.publish` hay `page_queue`; không sửa luồng hẹn Facebook.
- Không thêm cột `publications` (dùng lại các cột IG đã có: `remote_id`, `finish_sent_at`, `external_id`, `post_url`, `remote_mp4_key`, `post_text`).
- Không OAuth/kết nối Instagram riêng; không đăng Instagram không gắn Page.
- Không đọc số liệu, không bình luận Instagram, không Trial Reels/collab/ảnh.
- Không đổi hành vi đăng tay Instagram, TikTok auto, hay YouTube.
- Không lưu token thô ở bất cứ đâu; không đưa token ra frontend/log/response.

## 6. Kiểm thử

- Trước tiên chạy pytest publish Facebook, TikTok auto, Instagram hiện có (`api/tests/test_publish.py`, `test_tiktok_auto_post.py`, `test_instagram_publish.py`, `test_fanpages.py`) — đã đỏ sẵn thì dừng và báo, không xây tiếp trên nền đỏ.
- Fake Instagram đã có trong `api/scripts/fake_services.py` (theo brief IG §6) — dùng lại, không gọi Instagram thật.
- Test mới (gợi ý `api/tests/test_instagram_auto_post.py`, theo mẫu `test_tiktok_auto_post.py`): (1) bài Facebook hẹn giờ đã tới + Page auto bật + đã liên kết IG → có `Publication` Instagram `pending` + Job `ig_publish`, `post_text` đúng caption đã cắt, `remote_mp4_key` đúng MP4; (2) auto tắt → không tạo gì; (3) Page chưa liên kết IG → không tạo gì, không lỗi; (4) đã có bài Instagram của video ở `pending`/`scheduled`/`published`/`failed` → không tạo trùng (`cancelled` thì tạo được); (5) video đang có job → bỏ qua, vòng sau tạo; (6) bài Facebook quá 24 giờ → không tạo; (7) bài Facebook "Đăng ngay" (`scheduled_at` null) → không tạo; (8) video không có MP4 → không tạo; (9) route công tắc: không phải chủ Page → 403, Page chưa liên kết → 422, bật/tắt lưu được và hiện trong `_rows`; (10) Job IG lỗi không đụng bài Facebook; (11) video dài hơn 90 giây (ví dụ 113 giây như video 310) vẫn tạo bài bình thường — không có lọc độ dài; (12) video có hai bài Facebook đã tới giờ → chỉ một bài Instagram.
- Web: typecheck + lint sau khi sửa.

## 7. Tài liệu và việc tay của chủ sau khi merge

- `docs/decisions/2026-11-22-instagram-auto-post.md`: ghi 7 quyết định ở §2, nêu rõ đảo §5 brief IG.
- `docs/architecture.md` (cạnh đoạn `queue_tiktok_posts`, ~dòng 1216): thêm đoạn `queue_instagram_auto_posts` + `fanpages.instagram_auto`.
- `docs/specs/instagram-posting/brief.md` §5: ghi chú một dòng — "§5 đã đảo ngày 2026-11-22, xem brief auto-post" — không sửa nội dung cũ.
- Chủ tự làm sau merge (không phải việc của coding agent), theo đúng thứ tự:
  1. **Sửa token trước (bắt buộc, nếu không công tắc không bật được):** (a) quản trị viên app 'Reels Report Tool' thêm use case Instagram ở developers.facebook.com (kèm App Review / xác minh doanh nghiệp nếu Meta yêu cầu); (b) chỉ định tài khoản Instagram @tiemdoccomment cho System User ReelsStudioPublisher; (c) dán lại token Page có đủ quyền `instagram_basic` + `instagram_content_publish`; (d) kiểm tra trong tool: Page Tiệm hiện đã liên kết @tiemdoccomment, không còn dòng "Chưa liên kết Instagram".
  2. Mở Quản lý kênh, bật công tắc Instagram **chỉ cho Page Tiệm Đọc Comment**.
  3. Kiểm tra 1 video hẹn giờ: tới giờ Facebook lên thì Instagram lên sau khoảng 1 phút, caption và hashtag giống Facebook. Video 310 đã đăng tay lên @tiemdoccomment tối 22/11 là bằng chứng luồng API chạy được — bài auto đầu tiên chỉ cần khớp đúng link/caption như bài đó.
  4. Page Tôi Đọc chưa có IG liên kết nên chưa bật được — liên kết IG cho Page đó trước rồi mới bật, khi nào user quyết.

## 8. Thứ tự làm

0. (kiểm chứng, gộp vào test 11) Không chạy staging: fake service không kiểm được giới hạn của Meta, và bằng chứng live (reel 113,2 giây) đã có ở §3. Chỉ cần test (11) chứng minh vòng quét không lọc độ dài. Không gắn giới hạn độ dài vào code.
1. (a) Migration 0117 + model `Fanpage.instagram_auto` + route công tắc + test route.
2. (b) `jobs.queue_instagram_auto_posts` + gọi trong `worker.py queue_checks()` + test quét.
3. (c) Web: công tắc cạnh chỉnh TikTok auto + type `Fanpage` + typecheck/lint.
4. (d) File quyết định mới + `docs/architecture.md` + ghi chú §5 brief IG. Chạy lại toàn bộ test chạm tới sau mỗi bước.
