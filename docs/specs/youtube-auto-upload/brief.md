# Brief: tự đăng YouTube theo khung giờ Facebook, bật/tắt theo từng Page

## 0. Mục tiêu

Thêm công tắc `youtube_auto` cho từng Page (mặc định tắt). Khi bật, video nào của Page lên Facebook đúng khung giờ hẹn thì worker tự tải MP4 đó lên kênh YouTube đã chọn của Page, **ở chế độ riêng tư** — y hệt như bấm tay "Tải lên YouTube" hôm nay, chỉ khác là không cần bấm. Người dùng vẫn tự công khai video trong YouTube Studio.

Phạm vi bật đầu tiên: Tiệm Đọc Comment và Tôi Đọc Threads Để Bạn Không Phải Đọc (2 kênh YouTube đã kết nối tối 22/11). Các Page chưa chọn kênh thì không bật được công tắc.

Mọi khẳng định về code trong brief này đã đối chiếu với main ở SHA `4e4fa5fe` (merge PR #317, tối 22/11/2026).

## 1. Hiện trạng (đã kiểm chứng trên main)

- **Chưa có `youtube_auto` ở đâu cả.** `Fanpage` đã có 2 công tắc tự đăng theo cùng mẫu này: `tiktok_auto_mode: String(16), default="draft"` (migration 0084, `models.py:667`) và `instagram_auto: Boolean, default=False` (migration 0117, `models.py:670`). `Fanpage.youtube_channel_id: ForeignKey("channels.id")` đã có (migration 0097, `models.py:673`).
- **Đăng tay hôm nay** (`routes_youtube.py:131`, `POST /videos/{video_id}/upload`): kiểm tra MP4 đã render, kênh + connection tồn tại và thuộc về người bấm, `needs_reconnect` thì báo lỗi; chống trùng (cùng MP4 đã tải lên cùng kênh ở trạng thái private/scheduled/published → 409); tạo `Publication(platform="youtube", status="pending", channel_id, scheduled_at=planned, remote_mp4_key, caption=title, post_text=hashtags.post_text(caption, hashtags))` + `Job(kind="youtube_publish")`.
- **Worker tải lên** (`youtube_publish.py:30`, `run`): dùng lại đúng luồng này, không viết luồng tải mới. Lấy token qua `youtube_connections.access_token` (tự refresh khi sắp hết, sai số 5 phút); nối lại phiên tải dở qua `post.upload_url` đã lưu; metadata qua `youtube_upload.metadata` — tiêu đề qua `clean_title` (bỏ `<` `>`, tối đa 100 ký tự), mô tả bỏ `<` `>`, và **`"privacyStatus": "private"` cứng** (`youtube_upload.py:224`). Thành công: `external_id` = id video YouTube, `post_url` = link Shorts, `status = "private"`, `upload_url = None`.
- **`Publication.status = "private"`** nghĩa là video đã lên YouTube nhưng đang chờ người dùng công khai trong YouTube Studio; `scheduled_at` với YouTube chỉ là giờ dự định để nhắc, không phải giờ YouTube tự công khai (`models.py:902`, comment ở trường `status`).
- **Mẫu sweep có sẵn** (`jobs.py`): `queue_tiktok_posts` (dòng 1152) và `queue_instagram_auto_posts` (dòng 1214). Cả hai quét `Publication` Facebook ở trạng thái scheduled/published, `scheduled_at <= now()`, trong cửa sổ `TIKTOK_SWEEP_WINDOW = 24h` (dòng 1149); bỏ qua video không có MP4, Page không có chủ, job đang chạy (`videos.active_job`, `videos.py:208`), video đã có bài cùng nền tảng; tạo `Publication(status="pending")` + `Job` trong một `begin_nested`, bắt `IntegrityError` rồi bỏ qua. `worker.py:160` `queue_checks` chạy các sweep này khoảng mỗi phút.
- **Điểm khác biệt của 2 sweep cũ (giữ nguyên cho YouTube):** TikTok chặn trùng bằng `status IN (pending, scheduled, published)`; Instagram chặn trùng bằng `status != cancelled` — tức bài lỗi cũng không thử lại mỗi phút, người dùng bấm "Thử lại" (docstring `queue_instagram_auto_posts`). Dùng luật của Instagram.
- **Route mẫu** (`routes_fanpages.py`): `PUT /{fanpage_id}/tiktok-auto-mode` (dòng 312) và `PUT /{fanpage_id}/instagram-auto` (dòng 325) — chỉ chủ Page mới đổi được (403 `not_page_owner`); Instagram trả lỗi khi bật mà Page chưa liên kết Instagram (dòng 333). `_rows` trả `tiktok_auto_mode` (dòng 164) và `instagram_auto` (dòng 165) cho web.
- **Web mẫu:** kiểu `Fanpage` ở `web/src/lib/api.ts` (dòng 687–695: `tiktok_auto_mode`, `instagram_auto`, `youtube_channel`, `instagram`); công tắc nằm ở `web/src/components/actions/FanpageActions.tsx` — chọn TikTok dòng 113–119, công tắc Instagram dòng 131–139 (nhãn "Tự đăng Instagram: video hẹn giờ lên Facebook lúc nào, Instagram lên trong khoảng 1 phút sau đó." / "Chưa liên kết Instagram").
- **Token YouTube** (`youtube_connections.py`): `needs_reconnect` = `last_error is not None` (dòng 126); refresh token hết hạn thì `last_error` được ghi và mọi lần dùng sau đều báo `RECONNECT` ("Kết nối YouTube đã hết hạn, hãy bấm Kết nối YouTube lại ở Quản lý kênh"). App Google của tool đang ở chế độ thử nghiệm nên refresh token hết hạn sau 7 ngày — phải kết nối lại hằng tuần cho tới khi Google duyệt app (đã xác nhận tối 22/11, 2 kênh đều "Đã kết nối").
- **Giới hạn đứng yên:** video render tối đa 150s (quyết từ PR #315); YouTube Shorts không có cửa 90s như người ta tưởng.

## 2. Thiết kế

### 2.1 Migration 0118 (revises 0117)

Theo đúng mẫu file `api/migrations/versions/0117_fanpage_instagram_auto.py`: thêm cột `youtube_auto` kiểu Boolean, `nullable=False`, `server_default=false()` vào bảng `fanpages`, kèm `downgrade` xóa cột. Ghi chú trong file: tắt với mọi Page, chủ Page tự bật.

### 2.2 Model (`api/src/reels_api/models.py`, cạnh dòng 670)

```python
# On: a video of the Page that goes live on Facebook at its slot is also uploaded (private) to the Page's
# YouTube channel (migration 0118, jobs.queue_youtube_auto_posts).
youtube_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
```

### 2.3 Sweep (`api/src/reels_api/jobs.py`, cạnh `queue_instagram_auto_posts`)

Thêm `queue_youtube_auto_posts(db)`, gọi trong `worker.py:160` `queue_checks` ngay sau `queue_instagram_auto_posts`. Hành vi, sao y sweep Instagram:

- Quét `Publication` thỏa: `video_id IS NOT NULL`, `platform == "facebook"`, `status IN ("scheduled", "published")`, `scheduled_at <= now()`, `scheduled_at >= now() - TIKTOK_SWEEP_WINDOW` (dùng lại hằng số 24h, không tạo hằng số mới). Video "Đăng ngay" không có khung giờ nên không kích hoạt — giống Instagram.
- Với mỗi bài, bỏ qua khi: video không có `mp4_key`; Page không có `owner_id`; `page.youtube_auto` tắt; `page.youtube_channel_id` trống; không có connection (`youtube_connections.of_channel`) hoặc `connection.owner_id != page.owner_id`; `youtube_connections.needs_reconnect(connection)`; `active_job(db, video.id)` đang chạy; đã có `Publication` YouTube của video này trên cùng kênh với `status != "cancelled"` (bài lỗi cũng không thử lại — người dùng bấm "Thử lại" ở job lỗi, giống Instagram). Chặn theo video + kênh, không theo MP4 như route tay: video render lại (MP4 mới) sau khi đã tải lên thì sweep vẫn không tải lại — cố ý, khớp Instagram.
- Khi đủ điều kiện, trong một `begin_nested` (bắt `IntegrityError` rồi bỏ qua như 2 sweep cũ): tạo `Publication(platform="youtube", status="pending", fanpage_id=page.id, channel_id=page.youtube_channel_id, created_by_id=page.owner_id, remote_mp4_key=video.mp4_key, caption=title_of(video, title_scene), post_text=hashtags.post_text(video.caption, video.hashtags))` + `Job(kind="youtube_publish", status="queued", publication_id=...)`. Tiêu đề lấy bằng cùng `title_of` + `split_scenes` mà `routes_youtube.upload` đang dùng (không nhập tiêu đề tay — sweep không có người nhập); `clean_title` đã nằm trong `youtube_upload.metadata` nên không cần làm sạch thêm. `title_of`/`split_scenes` nằm trong `videos.py`, mà `jobs.py` đã import từ đó (`split_scenes`), nên chỉ cần thêm `title_of` vào dòng import, không gây import vòng.
- **Hàng đợi từng video:** `uq_jobs_active_video` (`models.py:547`) chỉ cho 1 job queued/running mỗi video, nên TikTok, Instagram và YouTube của cùng một video chạy lần lượt, mỗi sweep nhường khi video còn job. YouTube có thể lên chậm hơn vài phút so với khung giờ Facebook; cửa sổ 24h vẫn đủ. `scheduled_at` để `None`: giờ công khai vẫn do người dùng chọn tay trong YouTube Studio.
- **Không sửa `youtube_publish.run`, không thêm loại job mới, không đổi `privacyStatus`.** Sweep chỉ tạo bài + job rồi để worker hiện có tải lên.

### 2.4 Route (`api/src/reels_api/routes_fanpages.py`, cạnh dòng 325)

`PUT /api/fanpages/{id}/youtube-auto` nhận `{auto: bool}`, theo đúng mẫu `set_instagram_auto`: chỉ chủ Page (403 `not_page_owner`); khi `auto=true` mà Page chưa chọn kênh YouTube (`youtube_channel_id` trống) → lỗi 422, thông báo tiếng Việt "Page chưa chọn kênh YouTube, hãy chọn kênh rồi bật lại"; khi kênh đã chọn nhưng connection cần kết nối lại (`needs_reconnect`) → lỗi 422, thông báo đúng hằng `youtube_connections.RECONNECT` (cố ý khác câu có tên kênh của route tay). Trả về `_rows` như 2 route kia. Thêm `"youtube_auto": row.youtube_auto` vào `_rows` (cạnh dòng 165).

### 2.5 Web

- `web/src/lib/api.ts`: thêm `youtube_auto: boolean;` vào kiểu `Fanpage` (cạnh dòng 689).
- `web/src/components/actions/FanpageActions.tsx`: thêm công tắc ngay cạnh công tắc Instagram (dòng 131–139), gọi `PUT /fanpages/{id}/youtube-auto`. Nhãn khi bật: "Tự đăng YouTube: video hẹn giờ lên Facebook lúc nào, YouTube tải lên (riêng tư) ngay sau đó, thường trong vài phút." Khi Page chưa chọn kênh: "Tự đăng YouTube: Chưa chọn kênh YouTube". Khi kênh mất kết nối, dòng cảnh báo có sẵn "Kênh YouTube mất kết nối, hãy bấm Kết nối YouTube lại…" (dưới ô chọn kênh) đã báo chủ Page; không thêm cảnh báo thứ hai, vì sweep bỏ qua âm thầm nên dòng đó là chỗ duy nhất họ thấy.

### 2.6 Test (`api/tests/test_youtube_auto_post.py`, mới — theo mẫu `api/tests/test_instagram_auto_post.py`, 249 dòng của PR #317)

Bao phủ: bật/tắt công tắc (403 khi không phải chủ Page; 422 khi chưa chọn kênh; 422 khi connection cần kết nối lại); sweep tạo đúng 1 `Publication` YouTube + 1 job `youtube_publish` khi video tới giờ; không tạo trùng ở vòng quét sau; bỏ qua khi công tắc tắt / video chưa render / không có kênh / connection của người khác / connection hết hạn / đang có job chạy / đã có bài YouTube chưa hủy; bài có `scheduled_at` quá 24h không được gửi bù; video "Đăng ngay" không kích hoạt; bài tạo ra mang đúng `channel_id`, `remote_mp4_key`, tiêu đề và mô tả lấy từ video; Page bỏ chọn kênh sau khi đã bật công tắc thì sweep không tạo bài; Page đổi sang kênh khác thì video đã tải lên kênh cũ không chặn kênh mới.

### 2.7 Tài liệu

- `docs/architecture.md`: thêm một đoạn ngắn như PR #317 đã làm cho Instagram.
- `docs/decisions/2026-11-22-youtube-auto-post.md` (mới): ghi quyết định — tự đăng chỉ tải lên riêng tư, không tự công khai; giờ công khai do người dùng làm tay trong YouTube Studio; bật theo từng Page, mặc định tắt; 2 Page đầu là Tiệm và Tôi Đọc.

## 3. Không làm trong lần này

- Không đổi `privacyStatus` từ `private` sang công khai hay hẹn giờ công khai (`publishAt`). Đó là quyết định riêng, sau khi Google duyệt app (hiện app chưa duyệt nên video qua API vẫn phải giữ riêng tư).
- Không sửa route đăng tay `POST /videos/{video_id}/upload`, không sửa `youtube_publish.run`, không đụng tới TikTok/Instagram.
- Không gửi bù video cũ (quá 24h) và không tự đăng video "Đăng ngay".
- Không tự gia hạn token Google — việc kết nối lại vẫn làm tay (xem §4).

## 4. Việc tay của chủ Page sau khi merge + deploy

1. Ở "Quản lý kênh", kiểm tra mỗi Page đã chọn đúng kênh YouTube (Tiệm → Tiệm Đọc Comment, Tôi Đọc → Tôi Đọc Threads Để Bạn Không Phải Đọc — cả hai đã "Đã kết nối" tối 22/11).
2. Bật công tắc "Tự đăng YouTube" cho từng Page.
3. Kiểm tra đầu-cuối với 1 video hẹn giờ: Facebook lên → vài phút sau video xuất hiện trong YouTube Studio ở chế độ riêng tư, rồi công khai tay ở đó.
4. Nhớ: khi app Google còn ở chế độ thử nghiệm, token hết hạn sau 7 ngày — kết nối lại mỗi tuần; lúc đó sweep tự bỏ qua (không tạo job lỗi mỗi phút), lỗi hiện trên "Quản lý kênh" và ở dòng cảnh báo dưới ô chọn kênh của Page. Video lên Facebook trong lúc token chết sẽ được bù khi kết nối lại nếu còn trong 24h; quá 24h thì không tự bù, chủ Page tải tay bằng "Tải lên YouTube".

## 5. Chuẩn xong (theo AGENTS.md của repo)

Ruff + typecheck cho API, `npm run format && npm run lint && npm run typecheck` cho web, test mới phải chạy xanh (tại máy chỉ chạy các test mới/sửa; bộ đầy đủ và E2E để CI), docs trong `docs/` cập nhật cùng PR. Branch từ `main`, CI xanh mới merge; không đụng production trực tiếp.
