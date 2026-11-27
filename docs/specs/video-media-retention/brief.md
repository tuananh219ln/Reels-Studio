# Brief: Dọn media của video đã đăng sau 30 ngày (giữ mọi số liệu)

- Ngày: 26/11/2026. Người đề xuất: Nam dev. Trạng thái: bước 1 (báo cáo dung lượng, `python -m reels_api storage-report`, chỉ đọc) đã làm; các bước 2–6 **chờ chủ dự án chọn các điểm ở mục 7**.
- Đối chiếu với `main` @ `7b8f45a`. Mọi chỗ trỏ vào code dưới đây đã đọc trên commit đó.

## 1. Vấn đề

Mỗi video giữ file của nó trong một thư mục `videos/<id>/` trên volume chung của api và worker
(`config.storage_dir()`, `storage.DirectoryStorage`). Hiện **không có dọn dẹp nào**: file chỉ mất khi video bị xoá
hẳn (`routes_videos.py:661`, `delete_prefix`) ([deployment.md › Operations](../../deployment.md#operations):
"Deleting a video removes its folder for good; there is no other cleanup"). Ổ sẽ đầy dần.

Ý tưởng: sau 30 ngày, xoá **file media** của video đã đăng xong, giữ nguyên **mọi dòng trong database** (kịch bản,
cảnh, bài đăng, số liệu, QC, lịch sử duyệt) để thống kê và danh sách vẫn đúng.

## 2. Số liệu đo được và chưa đo được

**Đo được (qua MCP của app, chỉ đọc, 26/11):**

- 364 video đang có (id tới 460, tức khoảng 96 video đã bị xoá).
- Video cũ nhất còn lại: id 16–17, tạo ngày **01/11/2026**. Nghĩa là **chưa video nào quá 30 ngày**: luật 30 ngày
  sớm nhất chạm tới video đầu tiên khoảng 03/12 (30 ngày sau ngày đăng 03/11 của video 17).
- Nhịp làm video: khoảng **14 video/ngày** (364 video trong 26 ngày), gấp gần 5 lần con số "3 video/ngày" đang ghi
  trong `deployment.md`.

**Chưa đo được:** dung lượng thật trên volume production. Agent không được vào production (AGENTS.md: không terminal
Coolify, không DB production), và app chưa có chỗ nào báo dung lượng. Vì vậy bước 1 của việc này là một báo cáo dung
lượng (mục 5, bước 1) trước khi xoá bất cứ thứ gì.

**Ước tính từ code** (để có con số định hướng, cần báo cáo thật xác nhận):

| File trong `videos/<id>/` | Cột giữ key | Giới hạn trong code | Ước tính mỗi video |
|---|---|---|---|
| MP4 cuối (`video-*.mp4`) | `videos.mp4_key` (và `publications.remote_mp4_key`) | MP4 tải lên tối đa 200 MB (`remote_media.MAX_MP4_BYTES`) | 10–30 MB (deployment.md) |
| Clip từng cảnh | `scenes.video_key`, `scenes.motion.clip_key` | 50 MB/clip (`clips.MAX_CLIP_BYTES`) | 0–150 MB, tuỳ số cảnh dùng clip |
| Ảnh từng cảnh, ảnh gốc trước khi sửa | `scenes.image_key`, `scenes.image_original_key`, `scenes.motion.photo_key` | 15 MB/ảnh (`uploads.MAX_IMAGE_BYTES`) | 2–20 MB |
| Lời đọc | `scenes.voice_key` | | 0,5–3 MB |
| Nhạc riêng, ảnh lớp, âm thanh | `videos.music_key`, `scene_layers.image_key`, … | | 0–10 MB |
| Ảnh thu nhỏ | `videos.thumbnail_key` | | < 0,5 MB |

Với 14 video/ngày, tức khoảng 420 video/tháng, ước tính **15–80 GB/tháng**, phần lớn là clip cảnh và MP4.
Video kiểu "MP4 tải lên" (`mode = upload`, như loạt Muse gửi hôm nay) chỉ có MP4 và ảnh thu nhỏ.

Đã kiểm tra thêm: khi thay ảnh, clip, lời đọc hoặc render lại, file cũ **đã được xoá ngay** (vd. `jobs.py:738`,
`jobs.py:971`, `jobs.py:1663`), nên file mồ côi chỉ còn ở các trường hợp lỗi giữa chừng. Dọn file mồ côi vẫn nên có
nhưng không phải nguồn tốn chỗ chính.

## 3. Cái gì cần file nào (đọc từ code)

Đây là phần quan trọng nhất: xoá sai loại file sẽ làm hỏng một tính năng đang dùng.

| Việc | Cần file | Ghi chú |
|---|---|---|
| Thống kê, bảng "Bài đăng", danh sách, trang Thống kê, đọc số liệu Facebook/YouTube/TikTok | **Không** | Số liệu, `mp4_seconds`, `qc`, `words`, `voice_seconds` đều nằm trong DB. |
| Ảnh thu nhỏ ở danh sách | `thumbnail_key` | **Giữ.** |
| Xem MP4 trên trang video, "Tải MP4", "Xem khung hình bản render" (MCP) | MP4 | Mất MP4 thì phải hiện "Đã lưu trữ". |
| Đăng lên nền tảng khác về sau (YouTube, Instagram, TikTok, Page khác) | MP4 | Instagram đọc `remote_mp4_key or mp4_key` (`ig_publish.py:51`); TikTok đọc kích thước file (`tiktok_publish.py:81`). |
| Đặt ảnh bìa reel Facebook sau khi lên | MP4 của bài (`jobs.py:1115`) | Chỉ ngay lúc đăng; mất file thì Facebook tự chọn bìa, không lỗi. |
| **"Nhân bản y hệt", "Nhân bản xáo cảnh", "Bản TikTok"** | **Toàn bộ file cảnh** (ảnh, clip, lời đọc, lớp, nhạc) | `duplicate.copy_video` chép từng file cảnh (`duplicate.py:80`); **không chép MP4**, bản sao luôn render lại. |
| "Nhân bản" bằng AI (clone) | Chỉ nhạc | Kịch bản lấy từ DB; ảnh/clip tìm lại. |
| "Đã dùng trong nhóm" (lấy ảnh/clip của video khác cùng nhóm) | File cảnh của video kia | `GET /scenes/{id}/group-media`. Video đã dọn phải bị loại khỏi danh sách này. |
| Sửa cảnh rồi render lại | Toàn bộ file cảnh | Video đã dọn không render lại được nữa. |

**Hệ quả cho thiết kế:** ý "giữ MP4 của video thắng để nhân bản" chưa đủ. Nhân bản cần **file cảnh**, không cần MP4.
Video thắng phải giữ **cả file cảnh**. Ngược lại, với video thường, MP4 có ích hơn file cảnh (để đăng thêm nền tảng),
nên thứ tự "xoá file trung gian trước, MP4 sau" là đúng.

## 4. Thiết kế đề xuất

### 4.1 Hai mức dọn

| Mức | Xoá | Giữ | Khi nào (mặc định đề xuất) |
|---|---|---|---|
| **1. Dọn file dựng** | ảnh, clip, lời đọc, nhạc riêng, ảnh lớp, âm thanh của cảnh | MP4, ảnh thu nhỏ | 30 ngày sau lần đăng cuối |
| **2. Dọn MP4** | MP4 | ảnh thu nhỏ | 60 ngày sau lần đăng cuối |

Database **không đổi**: các cột key vẫn giữ nguyên giá trị (để biết video từng có gì), chỉ thêm dấu đã dọn. Bảng
`media_items` (Kho tư liệu), `music_tracks`, `references/`, `competitors/` nằm ngoài việc này.

### 4.2 Video nào được dọn

Một video vào diện dọn khi **tất cả** điều sau đúng:

1. Đã duyệt (`review_status = approved`) và có ít nhất một bài `published`.
2. **Không còn bài nào đang mở** ở bất kỳ nền tảng nào: không `pending`, `scheduled`, `pending_link`, `private`
   (YouTube chờ bật công khai), không TikTok còn ở "nháp" (`posted_states.tiktok = draft`), và không nằm trong hàng chờ
   của Page (`page_queue_items`).
3. Bài đăng gần nhất (`published_at` lớn nhất) đã quá 30 ngày (mức 1) hoặc 60 ngày (mức 2).
4. Không có job nào đang chạy hoặc chờ trên video.
5. Không phải video thắng, không được ghim "Giữ media" (4.3).

Video chưa từng đăng (nháp, bị từ chối, lỗi) **không bị đụng**, như đã thống nhất. Xem điểm 7.4 về video bỏ dở.

### 4.3 Giữ video thắng

- **Tự động:** video có bài `is_winner` (`analytics.is_winner`, hiện là ≥ 10 lần trung vị 48h của Page,
  `WINNER_TIMES = 10`), hoặc video đã là nguồn của bản sao còn tồn tại (`shuffled_from_id`, `variant_of_id` trỏ tới
  nó, hoặc bản "(copy)") trong 30 ngày qua.
- **Bằng tay:** nút **"Giữ media"** trên trang video và trên dòng danh sách (cột `videos.keep_media`). Bỏ ghim thì video
  quay lại luật thường, đếm từ lần đăng cuối.
- Ngưỡng 10 lần trung vị khá chặt, nên rất ít video sẽ tự được giữ. Xem điểm 7.2.

### 4.4 Báo trước 3 ngày

- Mỗi ngày worker tính danh sách "sắp dọn trong 3 ngày".
- **Telegram nhắn riêng** cho người làm video (đúng [decision 2026-11-26-telegram-private](../../decisions/2026-11-26-telegram-private.md):
  việc của từng người không gửi vào nhóm chung). Một tin gộp mỗi ngày, liệt kê video và nút/link "Giữ media". Không
  có Telegram thì chỉ hiện trên web.
- Trên web: thẻ "Sắp dọn media (n)" ở danh sách video của người đó, và nhãn "Media sẽ được dọn ngày dd/mm" trên trang
  video. Ngày hiển thị theo giờ Việt Nam.

### 4.5 Sau khi dọn, app hiển thị gì

- Danh sách, thống kê, bảng "Bài đăng": như cũ (ảnh thu nhỏ còn).
- Trang video: nhãn **"Đã lưu trữ media"** (mức 1) hoặc **"Đã lưu trữ cả MP4"** (mức 2). Ẩn hoặc khoá: sửa ảnh/clip
  cảnh, render, "Nhân bản y hệt", "Xáo cảnh", "Bản TikTok"; ở mức 2 khoá thêm xem/tải MP4 và đăng thêm nền tảng. Mỗi
  nút khoá nói lý do bằng tiếng Việt. "Nhân bản" AI vẫn dùng được (viết lại từ kịch bản).
- API và MCP trả lỗi rõ ("Media của video này đã được dọn ngày …") thay vì lỗi "không thấy file".
- "Đã dùng trong nhóm" bỏ qua video đã dọn.

### 4.6 Chạy thế nào

- Một job `media_cleanup` do worker chạy mỗi đêm (giờ VN, ví dụ 03:00), đúng luật "việc dài đi qua hàng job".
- Mỗi lần chạy có giới hạn số video (ví dụ 200) để không giữ worker quá lâu.
- Ghi lại cho từng video: `media_cleaned_at`, `media_cleaned_level` (1 hoặc 2), `media_freed_bytes`. Tổng dung lượng
  đã giải phóng xem được trên trang báo cáo.
- Biến môi trường để bật/tắt và chỉnh số ngày (`MEDIA_CLEANUP_ENABLED`, mặc định tắt khi mới deploy), thêm vào
  `.env.example` và bảng trong `deployment.md`. Hoặc để trong Cài đặt nhóm (điểm 7.5).
- Có chế độ chạy thử: tính và báo cáo, không xoá.

## 5. Các bước làm (mỗi bước một PR nhỏ)

1. **Báo cáo dung lượng, không xoá gì.** Một trang (hoặc thẻ trong Cài đặt) và lệnh `python -m reels_api storage-report`:
   tổng dung lượng theo loại file (MP4, clip, ảnh, lời đọc, khác), theo tuổi video (tuần), số file mồ côi, và
   "nếu bật luật thì giải phóng được bao nhiêu". Đây là con số thật mà brief này còn thiếu.
2. **Cột và luật chọn video** (migration: `keep_media`, `media_cleaned_at`, `media_cleaned_level`,
   `media_freed_bytes`), nút "Giữ media", nhãn "Sắp dọn". Chưa xoá.
3. **Báo trước** qua web và Telegram riêng.
4. **Job dọn mức 1**, bật bằng cờ, chạy thử trước một tuần.
5. **Khoá các nút** cho video đã dọn (web, API, MCP), cập nhật hướng dẫn trong app và `docs/architecture.md`,
   `docs/deployment.md`.
6. **Mức 2 (MP4)** sau khi mức 1 chạy ổn.

## 6. Trường hợp cần chú ý

- **Video đăng nhiều nơi, nhiều lần:** đếm từ bài đăng cuối, không phải bài đầu. Một bài mới (đăng thêm YouTube)
  làm lùi ngày dọn.
- **Bài Facebook đã hẹn giờ:** Facebook đã giữ file, nhưng app vẫn cần MP4 nếu phải "Thử lại". Còn bài hẹn giờ là chưa
  dọn.
- **Bài bị gỡ hoặc huỷ** (`deleted`, `cancelled`) không tính là đang mở, nhưng cũng không tính là "đã đăng" nếu đó là
  bài duy nhất. Video chỉ có bài đã gỡ được xem như chưa đăng.
- **Video "MP4 tải lên"** không có file dựng: mức 1 không giải phóng gì, chỉ mức 2.
- **Bản sao của video thắng** là video riêng với file riêng (chép, không dùng chung), nên dọn bản gốc không làm hỏng
  bản sao, và ngược lại.
- **Đang mở trang video lúc dọn:** job bỏ qua video có người đang mở chế độ "Chỉnh sửa" (`video_presence`) để không
  xoá dưới tay người đang sửa.
- **Lỗi giữa chừng:** xoá file trước, ghi dấu sau thì có thể mất file mà chưa có dấu. Nên ghi dấu "đang dọn" trước,
  xoá, rồi chốt. Lần chạy sau làm tiếp video dở dang.
- **Không khôi phục được:** không có bản sao lưu file (chỉ có dump DB). Xoá là mất hẳn. Xem điểm 7.3.
- **Muốn dùng lại ảnh/clip hay** của video sắp dọn: cách đúng là thêm vào Kho tư liệu (bản chép riêng), đã có sẵn.

## 7. Cần chủ dự án quyết

1. **Luật "chỉ người làm mới xoá"** ([decision 2026-11-09-delete-by-maker](../../decisions/2026-11-09-delete-by-maker.md)).
   Dọn tự động là app xoá file của mọi người mà không ai bấm. Đề xuất: coi đây là ngoại lệ có chủ ý (chỉ xoá file,
   không xoá video; có báo trước 3 ngày; ai cũng bấm "Giữ media" được), và ghi thành một decision mới. Cần anh đồng ý
   vì đây là nới một decision đã ghi.
2. **Thế nào là video thắng.** `is_winner` hiện là ≥ 10 lần trung vị, rất ít video đạt. Đề xuất: giữ tự động khi ≥ 3
   lần trung vị, cộng nút "Giữ media" bằng tay. Hoặc chỉ dùng nút bằng tay.
3. **Xoá hẳn hay chuyển sang kho rẻ.** `storage.py` đã chừa chỗ cho R2. Chuyển file cũ sang Cloudflare R2 (khoảng
   0,015 USD/GB/tháng, không tính phí tải về) thì vẫn khôi phục được, nhưng thêm một dịch vụ và khoá bí mật. Đề xuất:
   xoá hẳn trước, vì chỉ đụng video đã đăng, có báo trước và có "Giữ media"; cân nhắc R2 nếu báo cáo ở bước 1 cho thấy
   cần giữ nhiều.
4. **Video chưa đăng bị bỏ dở** (từ chối, lỗi, nháp lâu): không đụng (như đã nói), hay sau 60 ngày nhắn người làm hỏi
   xoá? Đề xuất: lần này không đụng, chỉ hiện trong báo cáo dung lượng để biết chúng chiếm bao nhiêu.
5. **Số ngày chỉnh ở đâu:** biến môi trường (đơn giản, cả app một luật) hay trong Cài đặt (đổi không cần deploy).
   Đề xuất: biến môi trường, 30 và 60 ngày.
6. **Mức 2 có làm không:** xoá MP4 sau 60 ngày làm mất khả năng đăng thêm nền tảng cho video cũ. Đề xuất: làm sau, khi
   báo cáo cho thấy MP4 chiếm đáng kể.

## 8. Không làm trong việc này

- Không dọn Kho tư liệu, Thư viện nhạc, video mẫu (`references/`), ảnh đối thủ (`competitors/`).
- Không đổi cách lưu file (vẫn thư mục trên volume).
- Không tự xoá video hay dòng nào trong database.
