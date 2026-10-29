---
# Creation date (YYYY-MM-DD)
created: 2026-10-29

# Status: draft | approved
status: draft

# Work type: feature | bug | refactoring
type: feature
---

# User-spec: web-video-render

> **Executor instruction.** If the project has Project Knowledge, first read its main `SKILL.md`,
> then only the materials it routes to for this task. Read `decisions.md` if it exists. Work from
> the root of the project this spec belongs to. Implement the entire user-spec. Use the execution
> skills appropriate to the work.

## What We Are Building

Luồng tạo video ngay trên web app (reels.quangdang.xyz). Thành viên nhập chủ đề. Claude viết kịch
bản theo cấu trúc của `samples/xuong-khop.json` gồm cảnh tiêu đề và các cảnh nội dung, kèm tiêu đề,
caption, hashtag, affiliate và gợi ý nhạc. App tự gán ảnh Pixabay cho từng cảnh. Thành viên sửa
kịch bản, đổi ảnh, thêm nhạc nếu muốn, rồi bấm Render. Video được render trên server bằng bộ
render hiện có (`worker/`, `reels_render.render_video`), chạy trong một service worker mới trên
Coolify. Kết quả là MP4 9:16 xem được ngay trên web và tải về được.

Spec này còn gồm:
- trang danh sách video;
- nhân bản video bằng Claude;
- trang Nhật ký job đơn giản (`/jobs`);
- trang `/knowledge` để sửa prompt Claude và danh sách từ cấm.

## Why

Hiện mỗi video tốn khoảng 30 phút làm tay: viết kịch bản trong Claude Project, tìm ảnh, dựng
CapCut. Bộ render đã có, nhưng chỉ chạy bằng dòng lệnh trên máy của chủ dự án, nên team không dùng
được. Sau tính năng này, cả team 5 người làm video trên web, từ chủ đề đến MP4 trong không quá 10
phút, và dùng chung một thư viện video.

## Expected Behavior

### Tạo video mới
1. Ở `/videos`, thành viên bấm "Tạo video", nhập chủ đề (VD "thực phẩm tốt cho xương khớp người
   sau 50 tuổi") rồi bấm "Viết kịch bản".
2. App tạo một video nháp và một job "viết kịch bản" trong hàng đợi. Trang video hiện trạng thái
   (Chờ thứ N / Đang viết) và tự cập nhật, không cần tải lại trang.
3. Worker gọi Claude. Prompt gồm phần nội dung sửa được trên `/knowledge`, danh sách từ cấm, và
   phần định dạng đầu ra cố định trong code. Claude trả về JSON gồm:
   - 5 tiêu đề viết hoa, mỗi tiêu đề ≤ 12 từ;
   - từ khóa tìm ảnh cho cảnh tiêu đề;
   - 5–7 cảnh nội dung. Mỗi cảnh có chữ trên màn hình (≤ 10 từ, `*từ*` để tô đỏ, xuống dòng bằng
     `\n`), số giây, từ khóa tìm ảnh tiếng Việt (cụ thể nhất trước) và prompt ảnh 9:16;
   - caption 80–120 từ và 5 hashtag;
   - 2 sản phẩm affiliate và câu bình luận ghim;
   - phần tự rà soát an toàn, liệt kê các câu đã sửa;
   - 2–3 gợi ý nhạc không lời hợp chủ đề (VD "Windy Hill").
4. Ngay trong job đó, worker tự gán ảnh Pixabay cho mọi cảnh chưa có ảnh, kể cả cảnh tiêu đề. Ảnh
   được tải về storage và chốt lại, nên render dùng đúng ảnh đã thấy. Nếu Pixabay lỗi (sai key,
   mạng, quá giới hạn, không có kết quả), kịch bản vẫn được lưu. Cảnh thiếu ảnh được đánh dấu đỏ
   kèm lý do.
5. Job xong thì trang video hiện trình soạn.

### Soạn và sửa
- **Cảnh tiêu đề:** chọn 1 trong 5 tiêu đề, hoặc tự sửa chữ. Cảnh này có ảnh riêng, độ dài riêng
  (mặc định 3 giây) và từ khóa riêng.
- **Cảnh nội dung:** sửa chữ, số giây, từ khóa và prompt ảnh. Thêm, xóa và đổi thứ tự cảnh.
- **Xem trước khung hình:** từng cảnh, kể cả cảnh tiêu đề, có ảnh xem trước gồm ảnh (cắt 9:16) và
  hộp chữ vàng, giống khung đầu của cảnh đó trong MP4. Ảnh được dựng bằng chính code của
  `reels_render`.
- **Ảnh mỗi cảnh:**
  - **Upload ảnh:** JPG/PNG/WebP, tối đa 15 MB.
  - **"Tìm lại ảnh":** tìm Pixabay theo từ khóa hiện tại và gán ngay.
  - **"Chọn từ Pixabay":** mở lưới ảnh nhỏ có dòng "Ảnh từ Pixabay". Ảnh nhỏ chỉ hiển thị tạm
    lúc xem. Ảnh được chọn mới tải bản lớn về server.
  - Lưới và "Tìm lại ảnh" chạy ngay, không xếp hàng sau render. Quá khoảng 10 giây hoặc lỗi thì
    báo lỗi tiếng Việt ngay tại cảnh đó.
- **Nhạc:** upload một file MP3 (≤ 20 MB). Có thể thay hoặc gỡ bất cứ lúc nào. Thanh âm lượng
  0–100%, mặc định 25%, lưu theo từng video. Không có MP3 thì video im lặng. Các gợi ý tên nhạc
  hiện ở trang video, sửa được và copy được, để thành viên chọn nhạc trong TikTok hoặc Facebook khi
  đăng.
- **Nội dung đăng:** caption, hashtag, affiliate, bình luận ghim và gợi ý nhạc đều sửa được. Phần
  tự rà soát chỉ để xem. Có nút copy "caption + hashtag" và nút copy bình luận ghim.
- **Tự lưu:** mỗi ô tự lưu khi rời ô và hiện "Đã lưu". Upload ảnh, chọn ảnh, thêm, xóa và đổi thứ
  tự cảnh được lưu ngay. Khi hai người sửa cùng một ô, bản lưu sau thắng. Sửa các ô khác nhau thì
  không đè lên nhau.
- **Cảnh báo từ cấm:** quét tiêu đề, chữ cảnh, caption và bình luận ghim. So khớp không phân biệt
  hoa thường, chuẩn hóa Unicode NFC và bỏ qua dấu `*`. Ô trúng từ cấm hiện cảnh báo vàng. Cảnh báo
  này không chặn render.

### Kiểm tra trước khi render
Áp dụng như nhau cho kịch bản Claude viết và bản thành viên sửa tay.

- **Chặn nút Render, hiện lý do ngay tại cảnh khi:**
  - không còn cảnh nội dung nào;
  - tiêu đề hoặc chữ của một cảnh trống;
  - chữ tràn hộp (theo đúng quy tắc vừa hộp của `reels_render`);
  - có cảnh thiếu ảnh;
  - số giây của một cảnh nằm ngoài 1–10;
  - tổng độ dài trên 90 giây.
- **Chỉ cảnh báo vàng, vẫn render được khi:**
  - số cảnh nội dung nằm ngoài 5–7;
  - tổng độ dài nằm ngoài 20–40 giây;
  - chữ một cảnh dài hơn 10 từ;
  - tiêu đề dài hơn 12 từ.

### Render
1. Bấm "Render" tạo một job render. Lúc bấm, app dùng dữ liệu đã lưu và chờ ô đang gõ lưu xong.
   Các job render chạy lần lượt, mỗi lần một job.
2. Trạng thái hiện Chờ thứ N, rồi Đang render, rồi Xong hoặc Lỗi, và tự cập nhật.
3. Trong lúc video có job chờ hoặc đang chạy, video bị khóa: không sửa và không xóa được. Bấm Render
   hay Viết kịch bản lần hai bị từ chối. Job còn chờ có nút "Hủy".
4. Xong thì trang video có trình phát MP4 (tua được) và nút tải MP4. Ảnh thu nhỏ của video là ảnh
   xem trước khung tiêu đề.
5. Sửa kịch bản sau khi đã render thì trang hiện nhãn vàng "MP4 chưa cập nhật theo bản sửa". MP4 cũ
   vẫn xem và tải được. Render lại thì MP4 cũ được giữ tới khi bản mới xong. Render lại lỗi thì MP4
   cũ vẫn còn.

### Nhân bản bằng Claude
- Trên một video, bấm "Nhân bản" và nhập yêu cầu đổi (bắt buộc), VD "đổi sang mốc 45 tuổi, tim
  mạch".
- App chụp lại dữ liệu lúc bấm, gồm chủ đề, kịch bản đã sửa và yêu cầu đổi. Từ đó tạo một video
  nháp mới với job "nhân bản". Video gốc không bị khóa.
- Claude giữ công thức của video gốc và viết kịch bản mới với đủ các phần như bước 3 ở trên. Worker
  tự gán Pixabay như video mới. MP3, âm lượng và gợi ý nhạc được chép sang bản nháp.

### Lỗi, hủy và job kẹt
- **Claude trả JSON hỏng, hoặc thiếu tiêu đề hay cảnh:** worker tự gọi lại Claude một lần. Vẫn
  hỏng thì job Lỗi.
- **Claude trả dữ liệu lệch nhẹ:** kịch bản vẫn được lưu và đi qua bước "Kiểm tra trước khi render".
  - Số giây < 1 thì đặt thành 4.
  - Từ khóa dài hơn 100 ký tự thì cắt bớt.
  - Thiếu gợi ý nhạc hoặc thiếu từ khóa tiêu đề thì để trống.
- **Mọi job lỗi:** hiện lý do bằng tiếng Việt dễ hiểu và có nút "Thử lại". Dữ liệu đã sửa được giữ
  nguyên. Ví dụ: Claude hết hạn mức, FFmpeg lỗi, "File nhạc không đọc được".
- **Job kẹt:** job chạy quá 15 phút, tính từ lúc bắt đầu chạy (không tính lúc chờ), tự chuyển Lỗi.
  Nếu sau đó worker mới xong thì kết quả bị bỏ.
- **Hủy job còn chờ:** job thành "Đã hủy".
  - Hủy job viết kịch bản hoặc nhân bản: video nháp rỗng vẫn nằm trong danh sách, có nút "Viết
    kịch bản" và nút "Xóa".
  - Hủy job render: video trở về như trước, MP4 cũ giữ nguyên.

### Danh sách video, Nhật ký job, Tri thức
- **`/videos`:** mỗi video có ảnh thu nhỏ (chưa có ảnh thì hiện ô xám có tiêu đề hoặc chủ đề), tiêu
  đề, trạng thái (Nháp / Chờ / Đang viết / Đang render / Xong / Lỗi), người tạo và ngày tạo. Có ô
  tìm theo tiêu đề hoặc chủ đề.
- **Xóa video:** hỏi xác nhận, rồi xóa hẳn video, cảnh, job và mọi file (ảnh, MP3, MP4, ảnh thu
  nhỏ). Không khôi phục được. Không xóa được khi video có job chờ hoặc đang chạy.
- **`/jobs`:** bảng mọi job gồm video, loại (Viết kịch bản / Nhân bản / Render), trạng thái, người
  bấm, lúc bắt đầu, thời lượng và lỗi. Bấm vào một dòng để mở video.
- **`/knowledge`:** sửa phần nội dung của prompt (giọng văn, đối tượng, công thức tiêu đề, kịch bản
  mẫu) và danh sách từ cấm.
  - Prompt trống thì không cho lưu.
  - Có nút "Khôi phục mặc định".
  - Prompt mặc định gồm Custom Instructions và "Prompt viết kịch bản" trong bản plan của chủ dự án
    (xem [content.md](../../.claude/skills/project-knowledge/references/content.md)), kèm
    `samples/xuong-khop.json` làm ví dụ đầu ra.
  - Từ cấm mặc định: "chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc trị", "khắc tinh".

## Acceptance Criteria
- [ ] Nhập chủ đề và bấm "Viết kịch bản": một job chạy và trang tự cập nhật. Khi job xong, video có
      5 tiêu đề, một cảnh tiêu đề, 5–7 cảnh nội dung có từ khóa, caption, 5 hashtag, 2 affiliate,
      bình luận ghim, phần tự rà soát và gợi ý nhạc. Mọi cảnh đều đã có ảnh Pixabay, trừ khi
      Pixabay lỗi.
- [ ] Khi Pixabay lỗi hoặc không có kết quả, kịch bản vẫn được lưu và cảnh thiếu ảnh hiện màu đỏ
      kèm lý do.
- [ ] Sửa chữ, giây, từ khóa; thêm, xóa và đổi thứ tự cảnh; chọn tiêu đề: tất cả được tự lưu và vẫn
      còn sau khi tải lại trang. Hai người sửa hai cảnh khác nhau cùng lúc thì không mất sửa của ai.
- [ ] Ảnh xem trước của một cảnh khớp với khung đầu của cảnh đó trong MP4: cùng ảnh, cùng hộp chữ,
      cùng vị trí.
- [ ] Upload ảnh JPG/PNG/WebP ≤ 15 MB và MP3 ≤ 20 MB thành công. File sai loại, quá cỡ, hoặc MP3
      giả (đuôi .mp3 nhưng byte đầu không phải MP3) bị từ chối với thông báo tiếng Việt.
- [ ] Lưới Pixabay có dòng "Ảnh từ Pixabay". Ảnh được chọn nằm trong storage của app, không dùng
      link Pixabay. Pixabay chậm quá khoảng 10 giây thì báo lỗi tại cảnh.
- [ ] Nút Render bị chặn đúng ở từng điều kiện chặn: giây 0,9 bị chặn, 1 và 10 qua, 10,1 bị chặn;
      tổng 90 giây qua, 91 giây bị chặn. Các cảnh báo vàng hiện đúng biên nhưng không chặn: 4 và 8
      cảnh, tổng 19 và 41 giây, 11 từ, tiêu đề 13 từ.
- [ ] Từ cấm (VD "CHỮA KHỎI", "*chữa* khỏi", hoặc chữ ở dạng NFD) hiện cảnh báo vàng ở ô trúng,
      và Render vẫn bấm được.
- [ ] Render xong thì MP4 phát được và tua được trên reels.quangdang.xyz, và tải về được. Với cùng
      kịch bản và cùng ảnh, MP4 trông như `xuong-khop.mp4` render trên máy: font, hộp vàng, chữ đỏ,
      Ken Burns.
- [ ] Video 25 giây render xong trên server trong không quá 50 giây (≤ 2× độ dài).
- [ ] Hai job render không bao giờ chạy cùng lúc. Bấm Render lần hai bị từ chối. Video có job chờ
      hoặc đang chạy thì không sửa và không xóa được. "Hủy" chuyển job thành "Đã hủy".
- [ ] Render lại lỗi thì MP4 cũ vẫn xem và tải được. Sửa sau khi render thì hiện nhãn "MP4 chưa cập
      nhật theo bản sửa".
- [ ] Job chạy quá 15 phút chuyển thành Lỗi, kết quả đến muộn bị bỏ. Job Lỗi có lý do tiếng Việt và
      nút "Thử lại".
- [ ] Claude trả JSON hỏng thì worker gọi lại một lần, vẫn hỏng thì job Lỗi.
- [ ] Nhân bản với yêu cầu đổi tạo ra một video nháp mới có kịch bản mới, ảnh Pixabay mới, và MP3
      cùng gợi ý nhạc được chép sang. Video gốc không đổi và không bị khóa.
- [ ] Danh sách video có ảnh thu nhỏ, trạng thái, người tạo, ngày, và tìm được theo tiêu đề hoặc
      chủ đề. Xóa video thì mọi file của nó biến mất khỏi storage.
- [ ] `/jobs` liệt kê mọi job kèm loại, trạng thái, người bấm, thời lượng và lỗi.
- [ ] `/knowledge` sửa và lưu được prompt cùng từ cấm, và job sau dùng bản mới. Prompt trống không
      lưu được. "Khôi phục mặc định" hoạt động.
- [ ] Mọi endpoint trả file (MP4, ảnh, ảnh thu nhỏ, MP3) trả 401 khi chưa đăng nhập.
- [ ] Một thành viên đi từ chủ đề đến MP4 trên reels.quangdang.xyz trong không quá 10 phút.

## Constraints
- **Không chạy việc dài trong request của api.** Gọi Claude, tự gán Pixabay và render đều chạy
  trong worker qua hàng đợi. Chỉ có lưới Pixabay và "Tìm lại ảnh" chạy đồng bộ trong api, với
  timeout khoảng 10 giây.
- **Hàng đợi là bảng `jobs` trong Postgres.** Worker lấy job bằng `SELECT … FOR UPDATE SKIP
  LOCKED` và chỉ chạy một job tại một thời điểm. Không dùng Redis.
- **Lưu file qua một lớp storage trung gian** (VD `storage.save()` và `storage.get()`). Hiện tại
  lớp này dùng thư mục `STORAGE_DIR=/data/storage`, mount chung vào api và worker. Sau này chuyển
  sang R2 chỉ phải đổi cấu hình, không sửa logic.
- **FFmpeg chỉ cài trong image worker.** api cài gói `reels_render` để dựng ảnh xem trước, kiểm tra
  chữ vừa hộp và tìm Pixabay. Gói này chỉ cần Pillow, không cần FFmpeg.
- **Bảo mật:**
  - Mọi endpoint mới yêu cầu đăng nhập (`current_member`).
  - Các phương thức đổi dữ liệu phải qua kiểm tra Origin như hiện có.
  - Tên file do server sinh. Không bao giờ đưa đường dẫn do client gửi vào renderer.
  - API key chỉ nằm trong biến môi trường.
- **Upload đi qua Cloudflare Worker proxy** (giới hạn body 100 MB, bộ nhớ 128 MB). Mỗi request chỉ
  upload một file, và api tự kiểm tra kích thước.
- **Pixabay:** không hotlink ảnh đã dùng. Hiện "Ảnh từ Pixabay" ở mọi nơi liệt kê kết quả.
- **Migration:** thêm migration Alembic `0002` chỉ thêm bảng mới, không sửa `users` và `sessions`.
  Worker khởi động khi bảng `jobs` chưa có thì chờ và thử lại, không sập.
- **Ngoài phạm vi:** TTS, thư viện nhạc chung, Knowledge Base đầy đủ (ngân hàng thực phẩm có
  duyệt), đề xuất 10 biến thể có xếp hạng, đăng bài, giới hạn số lần gọi Claude.

## Risks
- **Risk 1:** phát hoặc tua MP4 (Range, 206) không chạy qua OpenNext/Cloudflare proxy.
  **Mitigation:** kiểm tra thủ công ngay sau deploy. Nếu lỗi, chuyển nhánh phục vụ file của lớp
  storage sang link trực tiếp tới domain api, hoặc sang R2.
- **Risk 2:** api và worker không cùng thấy `/data/storage` trên Coolify. **Mitigation:** README
  ghi rõ cách mount một volume cho cả hai app. Kiểm tra sau deploy bằng cách upload ảnh rồi render
  video có ảnh đó.
- **Risk 3:** Claude trả dữ liệu sai định dạng. **Mitigation:** định dạng đầu ra cố định trong code,
  worker kiểm tra JSON, gọi lại một lần, tự sửa các lệch nhẹ, còn lại đưa qua quy tắc chặn/cảnh
  báo.
- **Risk 4:** chi phí Claude tăng không kiểm soát (không giới hạn số lần gọi). **Mitigation:** người
  dùng chấp nhận rủi ro này. Nhật ký `/jobs` cho thấy số lần gọi.
- **Risk 5:** ổ VPS đầy (khoảng 10–30 MB mỗi video). **Mitigation:** xóa video là xóa cứng mọi
  file. Lớp storage cho phép chuyển sang R2.
- **Risk 6:** MP3 có bản quyền do thành viên tự upload có thể bị tắt tiếng hoặc mất kiếm tiền.
  **Mitigation:** mặc định không có nhạc, và app gợi ý tên nhạc để chọn trong app TikTok hoặc
  Facebook khi đăng.
- **Risk 7:** worker chết giữa chừng làm job kẹt. **Mitigation:** job chạy quá 15 phút tự thành
  Lỗi, kết quả muộn bị bỏ, và job có nút Thử lại.

## Accepted Decisions
- Spec này gồm Claude viết kịch bản ở bản gọn: một prompt sửa được, chưa có Knowledge Base đầy đủ.
  Lý do: người dùng muốn có ngay luồng từ chủ đề đến video. Knowledge Base với ngân hàng thực phẩm
  có duyệt để spec sau. TTS và thư viện nhạc để sau nữa.
- Chọn bảng job trong Postgres thay cho Redis như trong tài liệu kiến trúc. Lý do: chỉ 1–3
  video/ngày, và bớt được một dịch vụ phải chạy.
- Lưu file vào thư mục chung trên VPS (`/data/storage`), qua một lớp storage trung gian để sau này
  chuyển sang R2 chỉ cần đổi cấu hình. Không chọn R2 ngay để triển khai đơn giản hơn.
- Ảnh Pixabay được chốt lúc soạn (lưu thành asset) thay vì chọn ngẫu nhiên mỗi lần render. Lý do:
  bản xem trước phải khớp MP4.
- Cảnh tiêu đề là một cảnh riêng có ảnh, giây và từ khóa riêng. Claude trả thêm từ khóa cho cảnh
  này. Không dùng lại ảnh cảnh 1.
- Nhạc: mặc định xuất video không nhạc, Claude gợi ý tên nhạc để chọn khi đăng. Thành viên vẫn có
  thể upload MP3 kèm âm lượng. Lý do: nhạc TikTok như "Windy Hill" có bản quyền và app không tải
  được.
- Nhân bản do Claude viết lại theo một yêu cầu đổi, tạo một bản nháp mới, không chép tay. Đề xuất
  10 biến thể có xếp hạng để giai đoạn sau.
- Render lại giữ bản MP4 mới nhất, và giữ MP4 cũ tới khi bản mới xong. Không lưu mọi phiên bản.
- Kiểm tra trước render: chỉ chặn khi có lỗi thật, các lệch khỏi công thức kênh chỉ cảnh báo. Lý do:
  để team được làm video ngắn hoặc dài khác chuẩn.
- Tự lưu từng ô thay cho một nút Lưu cả video. Lý do: tránh người lưu sau xóa sửa của người khác.
- Định dạng đầu ra của Claude cố định trong code. Thành viên chỉ sửa phần nội dung của prompt, nên
  một lần sửa prompt không làm hỏng mọi job.
- api cài gói `reels_render`: build context là gốc repo, Base Directory của app api trên Coolify
  đổi thành `/`. Lý do: ảnh xem trước và kiểm tra chữ dùng đúng code render, không chép code.
- Không giới hạn số lần gọi Claude. Người dùng không chọn tính năng này.

## Testing

**Unit tests:** cần.
- api (pytest, Claude và Pixabay giả lập):
  - quy tắc chặn và cảnh báo với các giá trị biên trong Acceptance Criteria;
  - so khớp từ cấm (hoa thường, NFC, dấu `*`);
  - kiểm tra file upload (loại, kích thước, byte đầu MP3);
  - lớp storage trên thư mục cục bộ.
- worker:
  - parse và chuẩn hóa đầu ra Claude: hợp lệ, JSON hỏng, các lệch nhẹ (giây < 1, từ khóa quá dài,
    thiếu gợi ý nhạc).

**Integration tests:** cần.
- api với Postgres thật (pytest):
  - migration `0002`;
  - tạo và sửa video, cảnh, tự lưu theo ô không đè ô khác;
  - khóa khi có job, không tạo job trùng, Hủy → Đã hủy;
  - xóa cứng dọn sạch file;
  - mọi endpoint file trả 401 khi chưa đăng nhập; kiểm tra Origin;
  - ảnh xem trước khung hình và ảnh thu nhỏ;
  - lưới Pixabay và "Tìm lại ảnh": thành công, quá thời gian, sai key;
  - cờ "MP4 chưa cập nhật" khi sửa sau render.
- worker pytest với Postgres thật. Thêm service Postgres vào job `worker` trong CI. Test commit
  thật, không bọc trong transaction.
  - nhận job tuần tự; Hủy tranh chấp với nhận job (SKIP LOCKED);
  - job chạy quá 15 phút thành Lỗi và kết quả muộn bị bỏ;
  - job viết kịch bản và nhân bản với Claude giả: hợp lệ; JSON hỏng → gọi lại → Lỗi; lệch nhẹ →
    lưu;
  - tự gán Pixabay giả, và Pixabay lỗi vẫn lưu kịch bản;
  - render thật bằng FFmpeg dùng đúng ảnh đã chốt;
  - render lỗi giữ MP4 cũ; MP3 hỏng → "File nhạc không đọc được";
  - worker chờ khi bảng `jobs` chưa có.

**E2E tests:** cần (Playwright).
- Claude và Pixabay giả bằng một server HTTP cục bộ. Trỏ tới nó qua biến môi trường base URL,
  không thêm cờ giả lập vào code production.
- Job `web` trong CI cài FFmpeg và venv worker, chạy worker thật.
- Các luồng:
  - tạo video → sửa cảnh → đổi ảnh → render → phát và tải MP4;
  - nhân bản;
  - `/jobs`;
  - `/knowledge`: sửa prompt và từ cấm.
- Cập nhật bài E2E "coming-soon" hiện có cho `/videos`, `/jobs` và `/knowledge`.
- `api/scripts/e2e_reset.py` dọn thêm các bảng mới.

## Verification

### Agent Verification

| Step | Expected Result |
|------|-----------------|
| 1. Chạy pytest của api và worker (Postgres, FFmpeg) | Tất cả qua |
| 2. Chạy `npm run typecheck`, `npm run e2e` và build OpenNext trong `web/` | Tất cả qua |
| 3. Chạy local api, worker và web với Claude và Pixabay thật (nếu có key trong `.env`), tạo video "thực phẩm tốt cho xương khớp người sau 50 tuổi", rồi render | MP4 9:16 tạo được, đo thời gian render ≤ 2× độ dài. So khung hình với `out/xuong-khop.mp4` |
| 4. Build image api (context gốc repo) và image worker bằng Docker | Cả hai build được. Image worker có `ffmpeg` và `ffprobe` |
| 5. Đọc README phần triển khai | Có đủ các bước thủ công trên Coolify, GitHub và Cloudflare (xem User Verification) |

### User Verification
- **Cấu hình Coolify (theo hướng dẫn trong README):**
  - đổi Base Directory của app api thành `/`;
  - tạo app worker (Dockerfile có FFmpeg) với webhook riêng;
  - tạo volume `/data/storage` và mount vào cả api và worker;
  - đặt biến môi trường cho worker: `ANTHROPIC_API_KEY`, `PIXABAY_API_KEY`,
    `STORAGE_DIR=/data/storage`, `DATABASE_URL`;
  - thêm biến cho api: `PIXABAY_API_KEY` và `STORAGE_DIR=/data/storage`.

  Thêm secret webhook của worker vào GitHub environment `production`. Bước này cần tài khoản
  Coolify và GitHub của chủ dự án, nên chỉ chủ dự án làm được.
- **Thử thật trên reels.quangdang.xyz:**
  - làm một video từ chủ đề đến MP4 và bấm giờ (≤ 10 phút);
  - upload một ảnh và một MP3;
  - phát và tua video;
  - so với `xuong-khop.mp4`.

  Bước này cần làm tay để kiểm tra những gì chỉ thấy trên hạ tầng thật: Cloudflare proxy, volume
  chung và tốc độ VPS.
