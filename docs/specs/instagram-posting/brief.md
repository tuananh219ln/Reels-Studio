# Brief: Đăng Instagram Reels bằng API, và chọn cả 4 nền tảng trong bảng "Đăng bài"

## 0. Bàn giao

- Đọc `AGENTS.md`, `docs/decisions.md` (mục 2026-11-08), `docs/decisions/2026-11-09-page-owner-posts.md`,
  `2026-11-13-tiktok-auto-post.md`, `2026-11-14-publish-panel.md`, `2026-11-14-video-editor-spec.md`,
  `2026-11-17-youtube-private-upload.md` trước khi sửa. Không gọi Instagram/Facebook/TikTok/YouTube thật trong test,
  không đụng production.
- Làm theo đúng thứ tự §8; chạy pytest liên quan sau mỗi bước, bước nào đỏ thì dừng và báo.
- Brief này đảo 3 quyết định cũ theo yêu cầu của tuananh219ln (2026-11-19) — ghi vào file quyết định mới
  `docs/decisions/YYYY-MM-DD-instagram-api-posting.md` trong cùng PR, nêu rõ từng chỗ đảo (§2).

## 1. Vấn đề

- Instagram Reels đang đăng tay: tải MP4, copy caption, đăng trong app Instagram, dán link về
  (`routes_manual_posts.py`, `ManualPostCard.tsx`). Tài khoản Instagram của team đã là Business/Creator và **đã liên
  kết với Fanpage**, nên đăng được qua Instagram Content Publishing API bằng chính token Page app đang giữ.
- Bảng "Đăng bài" (`StatusCard.tsx` › `Platforms`) chỉ cho tick Facebook và TikTok; YouTube Shorts và Instagram là
  hàng "Đăng tay" không có ô tick; chọn "Hẹn giờ" thì TikTok bị tắt.

Mục tiêu: một lần bấm **"Đăng lên N nền tảng"** gửi được cả 4 nền tảng, kể cả khi hẹn giờ.

## 2. Quyết định (ghi vào file quyết định mới)

1. **Instagram đi theo Fanpage, không có kết nối riêng.** Tài khoản Instagram là `instagram_business_account` của
   Page; token dùng là token Page đã lưu (mã hóa) trên `fanpages`. Không bảng kết nối mới, không OAuth.
2. **Chỉ chủ Page đăng Instagram của Page đó** (như Facebook, 2026-11-09).
3. **Cả 4 nền tảng đều có ô tick** trong bảng "Đăng bài". Đảo quyết định 2026-11-14 publish panel ("YouTube Shorts và
   Instagram … posted by hand, no checkbox") và 2026-11-14 video editor spec ("Hẹn giờ turns its [TikTok] tile off").
4. **Hẹn giờ:**
   - **Facebook**: như hiện tại (Facebook tự đăng đúng giờ).
   - **Instagram**: hẹn **như Facebook**: bài ở trạng thái `scheduled` với `scheduled_at`; đến giờ worker đăng.
     Instagram API không có hẹn giờ, nên việc chờ nằm ở app (vòng một phút của worker, như `queue_tiktok_posts`).
   - **TikTok** và **YouTube**: vẫn gửi **ngay** khi bấm, dù chọn "Hẹn giờ" — TikTok vào nháp, YouTube tải lên riêng tư
     (YouTube giữ giờ hẹn làm `scheduled_at` nhắc việc như hiện có). Gửi xong là báo **xong** như mọi nền tảng; không
     thêm lời giải thích nháp/riêng tư (người dùng tự hiểu).
5. **Đăng ngay Instagram là công khai** (API không có nháp).
6. **Cùng một MP4 lên một tài khoản Instagram một lần** (như "never the same MP4 twice on one Fanpage").
7. **Đợt này không đọc số liệu, không bình luận Instagram** (đợt 2: `instagram_manage_insights`,
   `instagram_manage_comments`). Không Trial Reels, không collab, không ảnh/carousel.
8. **"Đã đăng tay" vẫn giữ** trong ngăn "Tùy chọn khác" của tab Instagram và YouTube, làm đường dự phòng.

## 3. Sự thật về Instagram API (kiểm chứng lại trên tài liệu Meta khi bắt tay code — chỗ nào khác thì ghi lại)

- Qua Facebook Login, gọi trên `graph.facebook.com` (`config.facebook_api_url()`, cùng phiên bản). Token cần
  **`instagram_basic`, `instagram_content_publish`, `pages_read_engagement`** (có thể thêm `business_management`).
  Token đang lưu có thể chưa có quyền Instagram → dán lại token (§7).
- Tài khoản IG của Page: `GET /{page-id}?fields=instagram_business_account{id,username,profile_picture_url}`.
- Đăng Reel:
  1. `POST /{ig-user-id}/media` với `media_type=REELS`, `upload_type=resumable`, `caption`, `share_to_feed=true`
     (tùy chọn `thumb_offset` ms cho ảnh bìa) → `id` container.
  2. `POST https://rupload.facebook.com/ig-api-upload/{api-version}/{container-id}`, header
     `Authorization: OAuth <token>`, `offset: 0`, `file_size: <bytes>`, body là MP4 — **không cần link công khai**.
  3. `GET /{container-id}?fields=status_code,status` tới `FINISHED` (khác: `IN_PROGRESS`, `ERROR`, `EXPIRED`,
     `PUBLISHED`). Container hết hạn sau 24 giờ.
  4. `POST /{ig-user-id}/media_publish` với `creation_id` → `id` media.
  5. `GET /{media-id}?fields=permalink,timestamp`.
- Giới hạn: caption 2.200 ký tự, tối đa 30 hashtag. Số bài API mỗi 24 giờ có hạn
  (`GET /{ig-user-id}/content_publishing_limit`). Gặp giới hạn thì báo lỗi, KHÔNG retry vòng lặp.
- Không thấy tham số nhãn AI (kiểm chứng; nếu có thì bật như `is_aigc` TikTok / `containsSyntheticMedia` YouTube).

## 4. Thiết kế

### 4.1 Dữ liệu (migration mới — số tiếp theo trong `api/migrations/versions`, hiện là 0111)

- `fanpages`: thêm `instagram_user_id` (String 32, nullable), `instagram_username` (String 100, nullable), ghi khi
  kiểm tra token Page (`page_info` / lúc kết nối) bằng cách đọc thêm `instagram_business_account`.
- `publications`: dùng cột sẵn có — `platform="instagram"`, `fanpage_id`, `status` (`pending` | `scheduled` |
  `published` | `cancelled`), `scheduled_at`, `remote_id` = container id, `finish_sent_at` (đặt trước `media_publish`),
  `external_id` = media id, `post_url` = permalink, `remote_mp4_key`, `source="app_api"`. Không cột mới.
- Job kind mới **`ig_publish`** (`jobs.kind` là String 16; `instagram_publish` dài 17).

### 4.2 Client (`api/src/reels_api/instagram.py`, theo mẫu `facebook.py`)

- Dùng lại `facebook.Page`, `FacebookError`, `_send` và ánh xạ lỗi của `facebook.py` (không chép lại).
- Hàm: `account_of(page)`, `create_reel_container(...)`, `upload(...)`, `container_status(...)`, `publish(...)`,
  `permalink(...)`, `recent_media(...)`.
- Host upload qua env mới `INSTAGRAM_UPLOAD_URL` (mặc định `https://rupload.facebook.com/ig-api-upload`) để fake
  service chen vào; thêm vào `.env.example` và bảng `docs/deployment.md`.
- Thông báo lỗi: thiếu quyền (code 10/200) → "Token Page chưa có quyền đăng Instagram, hãy dán lại token có
  instagram_content_publish"; giới hạn → "Instagram đang giới hạn số bài đăng, thử lại sau"; Page chưa liên kết →
  "Page này chưa liên kết tài khoản Instagram Business".

### 4.3 Route

- `POST /api/instagram/videos/{video_id}/publish` (router mới `routes_instagram.py`), body
  `{fanpage_id, scheduled_at: datetime | null}`:
  - Chỉ chủ Page; Page active, có `instagram_user_id`; video có MP4 và không `mp4_outdated`.
  - `scheduled_at` phải ở tương lai (cùng ràng buộc với Facebook: dùng lại hàm kiểm tra giờ hẹn của Facebook).
  - Chưa có bài `instagram` của MP4 này trên cùng Page ở `pending`/`scheduled`/`published` → nếu có thì 409.
  - `scheduled_at = null` → Publication `pending` + Job `ig_publish`. Có giờ → Publication `scheduled`, không Job.
- `POST /api/instagram/posts/{id}/cancel`: hủy bài `scheduled` (người tạo hoặc chủ Page) → `cancelled`, không gọi API.
- "Thử lại" theo cách các job publish khác đang làm (`posts_board.PUBLISH_JOBS` thêm `"instagram": "ig_publish"`;
  `videos.py` thêm nhãn job "Đăng Instagram").

### 4.4 Worker

- **Đến giờ hẹn**: `jobs.queue_instagram_posts`, gọi trong vòng một phút của worker cạnh `queue_tiktok_posts`: bài
  `instagram` `scheduled` có `scheduled_at <= now` → `pending` + Job `ig_publish`. Trễ quá 24 giờ (worker tắt lâu) thì
  không đăng mà chuyển `cancelled` kèm lỗi "Quá giờ hẹn hơn 24 giờ, chưa đăng" để thành viên tự quyết.
  Video đang có job khác thì để vòng sau.
- **`ig_publish.py`** (gọi từ `jobs.py` như `youtube_publish`):
  1. Nạp MP4 theo `remote_mp4_key`; token Page.
  2. Chưa có `remote_id`: tạo container (caption = caption video + hashtag, cắt 2.200 ký tự, tối đa 30 hashtag) →
     **lưu `remote_id` và commit NGAY**, rồi upload.
  3. Poll `status_code` ~5 giây/lần, tối đa ~5 phút. `ERROR`/`EXPIRED` → job lỗi, xóa `remote_id` để thử lại tạo mới.
  4. `FINISHED` → đặt `finish_sent_at`, commit, `media_publish` → `external_id`, `post_url` (permalink),
     `status="published"`, `published_at`.
  5. **Thử lại không đăng trùng**: có `remote_id` → hỏi `status_code` trước. `PUBLISHED` (câu trả lời trước bị mất) →
     tìm media qua `recent_media` (khớp caption, sau `finish_sent_at`) rồi chốt; `FINISHED` → đăng tiếp;
     `IN_PROGRESS` → chờ tiếp.

### 4.5 Chỗ phải chặn để Instagram không lẫn với Facebook

Code cũ coi Publication có `fanpage_id` + `remote_id` là reel Facebook. Kiểm tra và lọc `platform == "facebook"` ở:
`metrics.py`, `comments_inbox.py`, `post_comments.py`, `pinned.py`, `comment_tracker.py`, `page_queue.py`,
`page_dashboard.py`, `queue_tiktok_posts` (chỉ quét bài Facebook), `queue_post_checks`, kiểm tra "MP4 đã lên Page
này" (`posted_fanpage_ids`), và nơi lấy link reel Facebook mới nhất cho `posted_links`. Mỗi chỗ có test chứng minh
bài Instagram không bị đọc số, bình luận, kiểm tra hay xóa như reel Facebook.

### 4.6 Web — bảng "Đăng bài" (`StatusCard.tsx` › `Platforms`)

- **Cả 4 hàng có ô tick** (`AUTO_PLATFORMS` gồm cả `youtube`, `instagram`); bỏ kiểu hàng "Đăng tay" gạch đứt trong
  bảng chọn. Lựa chọn nhớ trong `localStorage` như hiện có.
- **Bỏ `usable()`**: "Hẹn giờ" không tắt nền tảng nào nữa.
- Tài khoản cho từng nền tảng (dòng tài khoản dưới các hàng, như Facebook/TikTok hiện có):
  - Instagram: Instagram của Page Facebook đang chọn (hiện `@username`); Page chưa liên kết thì hàng báo
    "Page chưa liên kết Instagram" và không đăng được.
  - YouTube: kênh của Page (`fanpages.youtube_channel_id`), nếu không thì kênh duy nhất đã kết nối của thành viên;
    tiêu đề mặc định là tiêu đề video (như thẻ "Tải lên YouTube").
- Gửi theo thứ tự hiện có (`PostStep`, mỗi nền tảng một lời gọi):
  - Facebook: như hiện tại.
  - Instagram: `{fanpage_id, scheduled_at}` (null khi "Đăng ngay").
  - TikTok: `{account_id, mode: "draft"}` — gửi ngay cả khi "Hẹn giờ".
  - YouTube: route tải lên hiện có, giờ dự định = giờ hẹn nếu "Hẹn giờ", không thì như mặc định hiện tại — gửi ngay.
- Kết quả từng nền tảng: TikTok nháp tới hộp thư và YouTube tải lên riêng tư xong thì hiện **"Đã đăng"** như nền tảng
  khác (`platformResults`), không thêm chữ "nháp"/"riêng tư". Instagram hẹn giờ hiện "Đã hẹn giờ · dd/mm, hh:mm" như
  Facebook; trạng thái thẻ "Đã hẹn giờ" áp cho cả bài Instagram hẹn giờ.
- Nút: "Đăng lên N nền tảng" / "Hẹn đăng lên N nền tảng" như hiện có.
- Ngăn "Tùy chọn khác": tab Instagram có trạng thái bài app đăng (link, Hủy hẹn) và giữ "Đã đăng tay" thu gọn.
- **Quản lý Page**: mỗi Page hiện `@instagram_username` nếu đã liên kết, hoặc "Chưa liên kết Instagram".
- Cập nhật `docs/ux-guidelines.md` các đoạn nói "YouTube Shorts and Instagram … posted by hand" và "Hẹn giờ turns
  TikTok off".

## 5. Không làm

> §5 đã đảo ngày 2026-11-22, xem brief auto-post (`docs/specs/instagram-auto-post/brief.md`).

- Không OAuth/kết nối riêng cho Instagram; không đăng Instagram không gắn Page.
- Không đưa Instagram vào hàng chờ Page (`page_queue`) hay tự đăng theo khung giờ Facebook như TikTok auto-post.
- Không đọc số liệu, không bình luận Instagram, không Trial Reels/collab/ảnh.
- Không đổi cách đăng Facebook, nháp TikTok, tải lên riêng tư YouTube ở phía api — chỉ đổi bảng chọn trên web và thêm
  Instagram.

## 6. Kiểm thử

- Trước tiên chạy test publish Facebook, TikTok, YouTube, manual posts hiện có; đỏ sẵn thì dừng và báo.
- Fake Instagram trong `api/scripts/fake_services.py` (qua `FACEBOOK_API_URL` + `INSTAGRAM_UPLOAD_URL`):
  `instagram_business_account`, container, upload, `status_code` điều khiển được, `media_publish`, permalink, danh
  sách media, lỗi quyền, lỗi giới hạn.
- Test api (gợi ý `api/tests/test_instagram_publish.py`): (1) kiểm tra token ghi `instagram_user_id`/username;
  (2) không phải chủ Page → 403; Page chưa liên kết → lỗi rõ; (3) đăng ngay: `remote_id` lưu TRƯỚC upload, bài
  `published` có `external_id` + `post_url`; (4) hẹn giờ: bài `scheduled`, không Job; vòng worker trước giờ không làm
  gì, đến giờ tạo Job; trễ hơn 24 giờ → `cancelled`; (5) hủy hẹn → `cancelled`, không gọi API; (6) caption cắt
  2.200 ký tự / 30 hashtag; (7) container `ERROR` → lỗi, thử lại tạo container mới; (8) mất câu trả lời
  `media_publish` → thử lại không gọi lần hai, tìm lại media; (9) MP4 đã lên Page đó → 409; (10) lỗi quyền/giới hạn →
  đúng thông báo; (11) bài Instagram không bị các chỗ ở §4.5 đụng tới.
- E2E: tick đủ 4 nền tảng + "Hẹn giờ" → Facebook và Instagram "Đã hẹn giờ", TikTok và YouTube "Đã đăng"; "Đăng ngay"
  4 nền tảng → cả 4 "Đã đăng". Sửa các test e2e cũ đang khẳng định hàng YouTube/Instagram không có ô tick và "Hẹn giờ"
  tắt TikTok (đây là thay đổi hành vi có chủ đích, ghi trong PR).
- Web: format + lint + typecheck.

## 7. Việc tay của chủ (ngoài code)

- Meta app: thêm quyền `instagram_basic` + `instagram_content_publish`. App chưa qua App Review thì chỉ người có vai trò
  trong app dùng được → thêm các thành viên vào vai trò.
- Tạo token mới đủ quyền, dán lại ở Quản lý Page cho từng Page có Instagram; kiểm tra Page hiện `@username`.
- Đăng thử 1 video lên một tài khoản Instagram ít quan trọng (đăng ngay, rồi một lần hẹn giờ), mở Instagram kiểm tra
  caption, ảnh bìa, chất lượng.

## 8. Thứ tự làm

1. Client `instagram.py` + env `INSTAGRAM_UPLOAD_URL` + fake service + test client.
2. Migration (2 cột `fanpages`) + đọc Instagram khi kiểm tra token Page + test.
3. Route publish/hủy + `queue_instagram_posts` + worker `ig_publish` + chặn lẫn với Facebook (§4.5) + test.
4. Web: bảng "Đăng bài" 4 ô tick + hẹn giờ mới + tab Instagram + Quản lý Page + e2e.
5. File quyết định mới, `docs/architecture.md`, `docs/project.md` (bỏ dòng "Instagram … deferred"),
   `docs/ux-guidelines.md`, `docs/deployment.md`.
