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
bản theo cấu trúc của `samples/xuong-khop.json`: một cảnh tiêu đề và các cảnh nội dung, kèm tiêu
đề, caption, hashtag, affiliate và gợi ý nhạc. App tự gán ảnh Pixabay cho từng cảnh. Thành viên
sửa kịch bản, đổi ảnh, thêm nhạc nếu muốn, rồi bấm Render. Video được render trên server bằng bộ
render hiện có (`worker/`, `reels_render.render_video`), chạy trong một service worker mới trên
Coolify. Kết quả là MP4 9:16 xem được ngay trên web và tải về được.

Spec này còn gồm:
- trang danh sách video;
- nhân bản video bằng Claude;
- trang Nhật ký job đơn giản (`/jobs`);
- trang `/knowledge` để sửa prompt Claude và danh sách từ cấm.

Việc triển khai chia thành hai phần, mỗi phần một PR (xem "Thứ tự triển khai").

## Why

Hiện mỗi video tốn khoảng 30 phút làm tay: viết kịch bản trong Claude Project, tìm ảnh, dựng
CapCut. Bộ render đã có, nhưng chỉ chạy bằng dòng lệnh trên máy của chủ dự án, nên team không dùng
được. Sau tính năng này, cả team 5 người làm video trên web, từ chủ đề đến MP4 trong không quá 10
phút, và dùng chung một thư viện video. Thành viên nào cũng thấy và sửa được video của người khác.

## Expected Behavior

### Thứ tự triển khai
1. **Phần 1 — luồng chính (PR 1).** Gồm:
   - hạ tầng: worker, hàng đợi, storage, upload ảnh;
   - viết kịch bản bằng Claude và tự gán ảnh Pixabay;
   - trình soạn có tự lưu, xem trước khung hình và "Tìm lại ảnh";
   - kiểm tra trước khi render, render, phát và tải MP4;
   - nội dung đăng (caption, hashtag, affiliate, bình luận ghim, gợi ý nhạc) sửa và copy được;
   - danh sách video, xóa video, Hủy, Thử lại, job kẹt;
   - `/knowledge` với prompt viết kịch bản và từ cấm.

   Phần 1 được deploy và kiểm tra trên server trước.
2. **Phần 2 — phần mở rộng (PR 2).** Gồm:
   - lưới "Chọn từ Pixabay";
   - nhạc MP3 và âm lượng;
   - nhân bản bằng Claude và prompt nhân bản trên `/knowledge`;
   - trang `/jobs`.

Tiêu chí nghiệm thu bên dưới ghi rõ thuộc phần nào.

### Tạo video mới
1. Ở `/videos`, thành viên bấm "Tạo video", nhập chủ đề (VD "thực phẩm tốt cho xương khớp người
   sau 50 tuổi") rồi bấm "Viết kịch bản".
2. App tạo một video nháp và một job "viết kịch bản" trong hàng đợi. Trang video hiện trạng thái
   (Chờ thứ N / Đang viết) và tự cập nhật, không cần tải lại trang.
3. Worker gọi Claude. Prompt gồm ba phần:
   - "Prompt viết kịch bản" sửa được trên `/knowledge`, với chủ đề tự điền vào chỗ `[Chủ đề]`;
   - danh sách từ cấm;
   - phần định dạng đầu ra cố định trong code. Phần này có một ví dụ JSON đầy đủ mọi trường, dựng
     từ nội dung của `samples/xuong-khop.json` (chữ, giây, từ khóa) và không có đường dẫn ảnh.

   Claude trả về JSON gồm:
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
5. Job xong thì trang video hiện trình soạn. Cảnh tiêu đề mặc định dùng tiêu đề đầu tiên và dài 3
   giây.

### Soạn và sửa
- **Cảnh tiêu đề:** chọn 1 trong 5 tiêu đề, hoặc tự sửa chữ. Cảnh này có ảnh riêng, độ dài riêng
  (mặc định 3 giây) và từ khóa riêng.
- **Cảnh nội dung:** sửa chữ, số giây, từ khóa và prompt ảnh. Thêm, xóa và đổi thứ tự cảnh.
- **Xem trước khung hình:** từng cảnh, kể cả cảnh tiêu đề, có ảnh xem trước. Ảnh xem trước gồm ảnh
  đã gán (cắt 9:16) và hộp chữ vàng, ở độ zoom 1.00. Ảnh được dựng bằng chính code dựng hộp chữ và
  vị trí của `reels_render`, nên trùng với cách cảnh đó được dựng trong MP4.
  - Với cảnh tiêu đề, ảnh xem trước chính là khung đầu của MP4.
  - Với cảnh nội dung, MP4 có thêm hiệu ứng chuyển cảnh (crossfade 0,4 giây) và Ken Burns, nên chỉ
    giống về ảnh, hộp chữ và vị trí. Không so từng điểm ảnh.
- **Ảnh mỗi cảnh:**
  - **Upload ảnh:** JPG/PNG/WebP, tối đa 15 MB.
  - **"Tìm lại ảnh":** tìm Pixabay theo từ khóa hiện tại và gán ngay ảnh khác với ảnh đang dùng.
  - **"Chọn từ Pixabay"** (phần 2): mở lưới ảnh nhỏ có dòng "Ảnh từ Pixabay". Ảnh nhỏ chỉ hiển thị
    tạm lúc xem. Ảnh được chọn mới tải bản lớn về server.
  - Lưới và "Tìm lại ảnh" chạy ngay, không xếp hàng sau render. Quá khoảng 10 giây hoặc lỗi thì
    báo lỗi tiếng Việt ngay tại cảnh và giữ nguyên ảnh cũ.
- **Nhạc** (phần 2):
  - Upload một file MP3 (≤ 20 MB). Có thể thay hoặc gỡ bất cứ lúc nào.
  - Thanh âm lượng 0–100%, mặc định 25%, lưu theo từng video. Không có MP3 thì video im lặng.
- **Nội dung đăng:** caption, hashtag, affiliate, bình luận ghim và gợi ý nhạc đều sửa được. Gợi ý
  nhạc dùng để chọn nhạc trong TikTok hoặc Facebook khi đăng. Phần tự rà soát chỉ để xem. Có nút
  copy "caption + hashtag" (caption, dòng trống, rồi các hashtag cách nhau bằng dấu cách), nút copy
  bình luận ghim và nút copy gợi ý nhạc.
- **Tự lưu:** mỗi ô tự lưu khi rời ô và hiện "Đã lưu". Upload ảnh, chọn ảnh, thêm, xóa và đổi thứ
  tự cảnh được lưu ngay. Khi hai người sửa cùng một ô, bản lưu sau thắng. Sửa các ô khác nhau thì
  không đè lên nhau.
- **Lưu khi video vừa bị khóa:** B đang gõ một ô thì A bấm Render. Lần lưu của B bị từ chối, ô hiện
  "Video đang render, chưa lưu" và giữ nguyên chữ B đã gõ, để B lưu lại sau khi render xong.
- **Cảnh báo từ cấm:** quét tiêu đề, chữ cảnh, caption và bình luận ghim. So khớp không phân biệt
  hoa thường, chuẩn hóa Unicode NFC và bỏ qua dấu `*`. Ô trúng từ cấm hiện cảnh báo vàng. Cảnh báo
  này không chặn render.
- **Ảnh thu nhỏ của video:** là ảnh xem trước của cảnh tiêu đề. Ảnh được tạo ngay khi cảnh tiêu đề
  có ảnh, kể cả lúc video còn là nháp. Ảnh được tạo lại mỗi khi ảnh hoặc chữ của cảnh tiêu đề đổi.
  Chưa có ảnh thì danh sách hiện ô xám có tiêu đề hoặc chủ đề.

### Kiểm tra trước khi render
Áp dụng như nhau cho kịch bản Claude viết và bản thành viên sửa tay.

Cách đếm:
- **Số từ:** bỏ dấu `*`, thay `\n` bằng dấu cách, rồi đếm các cụm cách nhau bằng khoảng trắng.
- **Tổng độ dài:** cộng số giây của cảnh tiêu đề và mọi cảnh nội dung, giống timeline của bộ render.
- **Quy tắc 1–10 giây:** áp cho mọi cảnh, kể cả cảnh tiêu đề.

**Chặn nút Render, hiện lý do ngay tại cảnh khi:**
- không còn cảnh nội dung nào;
- tiêu đề hoặc chữ của một cảnh trống;
- chữ tràn hộp (theo đúng quy tắc vừa hộp của `reels_render`);
- có cảnh thiếu ảnh;
- số giây của một cảnh < 1 hoặc > 10;
- tổng độ dài > 90 giây.

**Chỉ cảnh báo vàng, vẫn render được khi:**
- số cảnh nội dung < 5 hoặc > 7;
- tổng độ dài < 20 hoặc > 40 giây;
- chữ một cảnh > 10 từ;
- tiêu đề > 12 từ.

### Render
1. Bấm "Render" tạo một job render. Lúc bấm, app dùng dữ liệu đã lưu và chờ ô đang gõ lưu xong.
   Các job render chạy lần lượt, mỗi lần một job.
2. Trạng thái hiện Chờ thứ N, rồi Đang render, rồi Xong hoặc Lỗi, và tự cập nhật.
3. Trong lúc video có job chờ hoặc đang chạy, video bị khóa: không sửa và không xóa được. Bấm Render
   hay Viết kịch bản lần hai bị từ chối. Job còn chờ có nút "Hủy".
4. Xong thì trang video có trình phát MP4 (tua được), nút tải MP4 và thời lượng của lần render đó.
5. Sau khi đã render, nếu sửa một thứ làm MP4 khác đi thì trang và danh sách hiện nhãn vàng "MP4
   chưa cập nhật theo bản sửa". Các thứ đó là: chữ, số giây, ảnh, thứ tự, thêm hoặc xóa cảnh, tiêu
   đề, MP3, âm lượng. Sửa caption, hashtag, affiliate, bình luận ghim, gợi ý nhạc, từ khóa hay prompt
   ảnh thì không bật nhãn. MP4 cũ vẫn xem và tải được. Render lại thì MP4 cũ được giữ tới khi bản
   mới xong.
6. Video đã có MP4 mà render lại bị lỗi hoặc bị hủy thì vẫn ở trạng thái "Xong", MP4 cũ vẫn dùng
   được. Lỗi thì có thêm nhãn nhỏ "Render lại lỗi" kèm lý do và nút Thử lại.

### Nhân bản bằng Claude (phần 2)
- Trên một video, bấm "Nhân bản" và nhập yêu cầu đổi, VD "đổi sang mốc 45 tuổi, tim mạch". Ô yêu
  cầu là bắt buộc. Để trống thì nút tạo bị vô hiệu và api từ chối.
- App chụp lại dữ liệu ngay lúc bấm, gồm chủ đề, kịch bản đã sửa và yêu cầu đổi. App cũng chép
  riêng file MP3 (thành asset mới của bản nháp), âm lượng và gợi ý nhạc. Từ đó app tạo một video
  nháp mới với job "nhân bản". Video gốc không bị khóa. Xóa hay sửa video gốc sau đó không ảnh hưởng
  bản nháp.
- Claude giữ công thức của video gốc và viết kịch bản mới với đủ các phần như bước 3 ở trên. Worker
  tự gán Pixabay như video mới. Prompt dùng ô "Prompt nhân bản" trên `/knowledge`, cộng danh sách
  từ cấm và phần định dạng đầu ra cố định.
- Hủy job nhân bản rồi bấm "Viết kịch bản" trên bản nháp đó thì chạy lại đúng job nhân bản, với dữ
  liệu đã chụp và yêu cầu đổi cũ. MP3 đã chép vẫn giữ.

### Lỗi, hủy và job kẹt
- **Claude trả JSON hỏng, thiếu tiêu đề, hoặc không có cảnh nội dung nào:** worker tự gọi lại
  Claude một lần. Vẫn hỏng thì job Lỗi.
- **Claude trả dữ liệu lệch nhẹ:** kịch bản vẫn được lưu và đi qua bước "Kiểm tra trước khi render".
  - Số giây < 1 thì đặt thành 4.
  - Từ khóa dài hơn 100 ký tự thì cắt còn 100.
  - Thiếu gợi ý nhạc hoặc thiếu từ khóa tiêu đề thì để trống.
  - Ít hơn 5 tiêu đề thì lưu số đang có.
- **Mọi job lỗi:** hiện lý do bằng tiếng Việt dễ hiểu và có nút "Thử lại". Dữ liệu đã sửa được giữ
  nguyên. Ví dụ: Claude hết hạn mức, FFmpeg lỗi, "File nhạc không đọc được".
- **Chi tiết lỗi để chẩn đoán:** job lưu thêm chi tiết kỹ thuật, gồm đoạn cuối stderr của FFmpeg,
  câu trả lời thô của Claude khi parse lỗi và loại lỗi Pixabay. Trang video có mục "Chi tiết lỗi"
  thu gọn. Worker cũng ghi các chi tiết này ra log, kèm số token của mỗi lời gọi Claude.
- **Job kẹt:** mỗi job chạy trong một tiến trình con riêng. Job chạy quá 15 phút, tính từ lúc bắt
  đầu chạy (không tính lúc chờ), bị worker dừng hẳn: worker giết cả tiến trình con lẫn FFmpeg do nó
  mở, rồi chuyển job sang Lỗi. Job bị dừng không ghi thêm gì vào database hay storage. Chỉ sau khi
  tiến trình cũ đã dừng hẳn, worker mới nhận job tiếp theo, không cần ai khởi động lại. Mọi lời gọi
  ngoài (Claude, Pixabay) đều có timeout riêng.
- **Worker khởi động lại giữa chừng** (deploy mới, hết RAM, VPS khởi động lại): khi khởi động,
  worker chuyển mọi job đang chạy dở thành Lỗi "Worker khởi động lại giữa chừng" và mở khóa video.
  Worker không tự chạy lại job đó, để tránh gọi Claude tốn tiền ngoài ý muốn. Thành viên bấm Thử
  lại.
- **Hủy job còn chờ:** job thành "Đã hủy".
  - Hủy job viết kịch bản hoặc nhân bản: video nháp rỗng vẫn nằm trong danh sách, có nút "Viết
    kịch bản" và nút "Xóa".
  - Hủy job render: video trở về như trước, MP4 cũ giữ nguyên.

### Danh sách video, Nhật ký job, Tri thức
- **`/videos`:** mọi thành viên thấy mọi video. Mỗi video có ảnh thu nhỏ, tiêu đề, trạng thái (Nháp
  / Chờ / Đang viết / Đang render / Xong / Lỗi) cùng các nhãn phụ, người tạo và ngày tạo. Có ô tìm
  theo tiêu đề hoặc chủ đề.
- **Xóa video:** hỏi xác nhận, rồi xóa hẳn video, cảnh, job và mọi file (ảnh, MP3, MP4, ảnh thu
  nhỏ). Không khôi phục được. Không xóa được khi video có job chờ hoặc đang chạy.
- **`/jobs`** (phần 2): bảng mọi job gồm video, loại (Viết kịch bản / Nhân bản / Render), trạng
  thái (gồm "Đã hủy"), người bấm, lúc bắt đầu, thời lượng, số lần gọi Claude và lỗi. Bấm vào một
  dòng để mở video.
- **`/knowledge`:** có hai ô prompt và danh sách từ cấm.
  - Ô "Prompt viết kịch bản" (phần 1). Mặc định là mục "Ô 1" trong
    [default-prompt.md](default-prompt.md): Custom Instructions, Prompt viết kịch bản, công thức
    tiêu đề và lưu ý an toàn, chép nguyên văn từ bản plan của chủ dự án.
  - Ô "Prompt nhân bản" (phần 2). Mặc định là mục "Ô 2" trong [default-prompt.md](default-prompt.md),
    tức bản một biến thể của prompt nhân bản trong plan.
  - Ô trống thì không cho lưu. Mỗi ô có nút "Khôi phục mặc định" riêng.
  - Từ cấm mặc định: "chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc trị", "khắc tinh".

## Acceptance Criteria

### Phần 1
- [ ] Nhập chủ đề và bấm "Viết kịch bản": một job chạy và trang tự cập nhật. Khi job xong, video có
      5 tiêu đề, cảnh tiêu đề dài 3 giây dùng tiêu đề đầu tiên, 5–7 cảnh nội dung có từ khóa,
      caption, 5 hashtag, 2 affiliate, bình luận ghim, phần tự rà soát và gợi ý nhạc. Mọi cảnh đều
      đã có ảnh Pixabay, trừ khi Pixabay lỗi.
- [ ] Khi Pixabay lỗi hoặc không có kết quả, kịch bản vẫn được lưu và cảnh thiếu ảnh hiện màu đỏ
      kèm lý do.
- [ ] "Tìm lại ảnh" gán một ảnh Pixabay khác với ảnh đang dùng. Khi Pixabay lỗi hoặc chậm quá khoảng
      10 giây, app báo lỗi tại cảnh và giữ ảnh cũ.
- [ ] Sửa chữ, giây, từ khóa; thêm, xóa và đổi thứ tự cảnh; chọn tiêu đề: tất cả được tự lưu và vẫn
      còn sau khi tải lại trang. Hai người sửa hai cảnh khác nhau cùng lúc thì không mất sửa của ai.
- [ ] Thành viên B thấy, sửa và render được video do thành viên A tạo.
- [ ] Ảnh xem trước của cảnh tiêu đề gần trùng khung đầu (t = 0) của MP4: chênh lệch trung bình mỗi
      kênh màu ≤ 3/255. Ảnh xem trước của cảnh nội dung dùng đúng ảnh đã gán và đúng ảnh hộp chữ mà
      render dùng cho cảnh đó.
- [ ] Ảnh thu nhỏ được tạo khi cảnh tiêu đề có ảnh, kể cả với video nháp, và đổi theo khi ảnh hoặc
      chữ tiêu đề đổi.
- [ ] Upload ảnh JPG/PNG/WebP ≤ 15 MB thành công. File sai loại hoặc quá cỡ bị từ chối với thông
      báo tiếng Việt.
- [ ] Render bị chặn và lý do hiện tại cảnh trong từng trường hợp: xóa hết cảnh nội dung; để trống
      tiêu đề hoặc chữ một cảnh; chữ tràn hộp; có cảnh thiếu ảnh. Gỡ nguyên nhân thì Render bấm
      được lại.
- [ ] Biên của các quy tắc chặn Render:
  - giây mỗi cảnh: 0,9 bị chặn; 1 và 10 qua; 10,1 bị chặn (áp cả cho cảnh tiêu đề);
  - tổng độ dài (tính cả cảnh tiêu đề): 90 giây qua, 91 giây bị chặn.
- [ ] Biên của các cảnh báo vàng (không chặn Render):
  - số cảnh: 4 và 8 có cảnh báo; 5 và 7 không;
  - tổng độ dài: 19 và 41 giây có cảnh báo; 20 và 40 không;
  - chữ cảnh: 11 từ có cảnh báo, 10 từ không;
  - tiêu đề: 13 từ có cảnh báo, 12 từ không.
- [ ] Từ cấm (VD "CHỮA KHỎI", "*chữa* khỏi", hoặc chữ ở dạng NFD) hiện cảnh báo vàng ở ô trúng,
      và Render vẫn bấm được.
- [ ] Render xong thì MP4 phát được và tua được trên reels.quangdang.xyz, và tải về được.
- [ ] Render qua đường server (dữ liệu video và cảnh trong database, ảnh trong storage) với nội dung
      của `samples/xuong-khop.json` và ảnh của nó cho MP4 giống MP4 do CLI
      `python -m reels_render samples/xuong-khop.json -o <file>.mp4` tạo ra: cùng độ dài, cùng kích thước
      1080×1920, khung hình ở giữa mỗi cảnh chênh lệch trung bình ≤ 3/255.
- [ ] Trên server, video khoảng 25 giây render xong trong không quá 2× độ dài, theo thời lượng
      render hiện ở trang video.
- [ ] Hai job không bao giờ chạy cùng lúc. Bấm Render lần hai bị từ chối. Video có job chờ hoặc
      đang chạy thì không sửa và không xóa được.
- [ ] Hủy job viết kịch bản để lại video nháp rỗng có nút "Viết kịch bản" và "Xóa". Hủy job render
      giữ MP4 cũ. Cả hai job đều có trạng thái "Đã hủy".
- [ ] Render lại lỗi thì video vẫn "Xong" kèm nhãn "Render lại lỗi", MP4 cũ vẫn xem và tải được.
      Sau khi render, sửa chữ cảnh thì hiện nhãn "MP4 chưa cập nhật theo bản sửa", còn sửa caption
      thì không.
- [ ] B đang gõ thì A bấm Render: lần lưu của B bị từ chối với thông báo "Video đang render, chưa
      lưu", và chữ B đã gõ vẫn còn trong ô.
- [ ] Job chạy quá 15 phút bị dừng hẳn (không còn tiến trình FFmpeg nào của nó) và chuyển thành
      Lỗi. Job đó không ghi thêm gì. Job kế tiếp trong hàng chạy được mà không cần khởi động lại
      container. Job Lỗi có lý do tiếng Việt, mục "Chi tiết lỗi" và nút "Thử lại".
- [ ] Khởi động lại worker khi đang có job chạy: job đó thành Lỗi "Worker khởi động lại giữa
      chừng", video được mở khóa, và job không tự chạy lại.
- [ ] Claude trả JSON hỏng, thiếu tiêu đề hoặc không có cảnh thì worker gọi lại một lần, vẫn hỏng
      thì job Lỗi. Đầu ra có giây 0,5 được lưu thành 4. Từ khóa 150 ký tự được cắt còn 100.
- [ ] Danh sách video có ảnh thu nhỏ, trạng thái, nhãn phụ, người tạo, ngày, và tìm được theo tiêu
      đề hoặc chủ đề. Xóa video thì mọi file của nó biến mất khỏi storage.
- [ ] `/knowledge` sửa và lưu được "Prompt viết kịch bản" cùng từ cấm, và job sau dùng bản mới.
      Prompt trống không lưu được. "Khôi phục mặc định" đưa ô về đúng mục "Ô 1" của
      `default-prompt.md`.
- [ ] Gợi ý nhạc hiện ở trang video và sửa được. Nút copy "caption + hashtag", nút copy bình luận
      ghim và nút copy gợi ý nhạc chép đúng nội dung đang lưu.
- [ ] Mọi endpoint trả file (MP4, ảnh, ảnh thu nhỏ, MP3) trả 401 khi chưa đăng nhập.
- [ ] Một thành viên đi từ chủ đề đến MP4 trên reels.quangdang.xyz trong không quá 10 phút.

### Phần 2
- [ ] Lưới "Chọn từ Pixabay" có dòng "Ảnh từ Pixabay". Ảnh được chọn nằm trong storage của app,
      không dùng link Pixabay. Pixabay chậm quá khoảng 10 giây thì báo lỗi tại cảnh.
- [ ] Upload MP3 ≤ 20 MB thành công. File quá cỡ hoặc MP3 giả (đuôi .mp3 nhưng byte đầu không phải
      ID3 hay MPEG frame) bị từ chối.
- [ ] Thay MP3, gỡ MP3 (render ra bản im lặng) và đổi âm lượng (mặc định 25%, lưu theo video) đều
      phản ánh đúng trong MP4. MP3 hỏng lúc render cho job Lỗi "File nhạc không đọc được".
- [ ] Sau khi render, đổi MP3 hoặc âm lượng thì bật nhãn "MP4 chưa cập nhật theo bản sửa".
- [ ] Nhân bản với yêu cầu đổi tạo ra một video nháp mới có kịch bản mới và ảnh Pixabay mới, kèm
      bản chép của MP3, âm lượng và gợi ý nhạc. Yêu cầu trống bị từ chối. Video gốc không đổi,
      không bị khóa. Xóa video gốc sau khi bấm không làm mất nhạc của bản nháp.
- [ ] Hủy job nhân bản còn chờ rồi bấm "Viết kịch bản" trên bản nháp đó thì chạy lại job nhân bản
      với yêu cầu đổi cũ, và MP3 đã chép vẫn còn.
- [ ] Ô "Prompt nhân bản" trên `/knowledge` sửa và lưu được, và job nhân bản sau dùng bản mới. "Khôi
      phục mặc định" đưa ô về mục "Ô 2" của `default-prompt.md`.
- [ ] `/jobs` liệt kê mọi job kèm loại, trạng thái (gồm "Đã hủy"), người bấm, thời lượng và lỗi.
      Bấm một dòng thì mở video.

## Constraints
- **Không chạy việc dài trong request của api.** Gọi Claude, tự gán Pixabay và render đều chạy
  trong worker qua hàng đợi. Chỉ có lưới Pixabay và "Tìm lại ảnh" chạy đồng bộ trong api, với
  timeout khoảng 10 giây.
- **Hàng đợi là bảng `jobs` trong Postgres.** Worker lấy job bằng `SELECT … FOR UPDATE SKIP
  LOCKED` và chỉ chạy một job tại một thời điểm. Không dùng Redis.
- **Code của service worker** (vòng lặp nhận job, job viết kịch bản, nhân bản, render) nằm trong gói
  `reels_api` và chạy bằng một lệnh riêng, VD `python -m reels_api worker`. Nhờ vậy model, migration
  và cấu hình database chỉ có một bản. `reels_render` giữ nguyên là thư viện chỉ cần Pillow.
  - Image api gồm `reels_api` và `reels_render`, không có FFmpeg.
  - Image worker gồm `reels_api`, `reels_render` và FFmpeg ≥ 4.3 (cùng `ffprobe`).
  - Cả hai image build từ gốc repo.
- **Lưu file qua một lớp storage trung gian** (VD `storage.save()` và `storage.get()`). Trong spec
  này chỉ làm backend thư mục: `STORAGE_DIR=/data/storage`, mount chung vào api và worker.
  Renderer và Pillow vẫn làm việc với file cục bộ. Sau này thêm backend R2 thì chỉ cần viết thêm
  backend đó và đổi cấu hình, không sửa logic nghiệp vụ (video, cảnh, job).
- **Bảo mật:**
  - Mọi endpoint mới yêu cầu đăng nhập (`current_member`).
  - Các phương thức đổi dữ liệu phải qua kiểm tra Origin như hiện có.
  - Tên file do server sinh. Không bao giờ đưa đường dẫn do client gửi vào renderer.
  - API key chỉ nằm trong biến môi trường.
- **Upload đi qua Cloudflare Worker proxy** (giới hạn body 100 MB, bộ nhớ 128 MB). Mỗi request chỉ
  upload một file, và api tự kiểm tra kích thước.
- **Pixabay:** không hotlink ảnh đã dùng. Hiện "Ảnh từ Pixabay" ở mọi nơi liệt kê kết quả.
- **Migration:** thêm migration Alembic `0002` chỉ thêm bảng mới, không sửa `users` và `sessions`.
  Worker khởi động khi bảng `jobs` chưa có thì chờ và thử lại, không sập. Khi deploy, api (chạy
  migration) đi trước worker.
- **Ngoài phạm vi:** TTS, thư viện nhạc chung, Knowledge Base đầy đủ (ngân hàng thực phẩm có
  duyệt), đề xuất 10 biến thể có xếp hạng, đăng bài, giới hạn số lần gọi Claude.

## Risks
- **Risk 1:** phát hoặc tua MP4 (Range, 206) không chạy qua OpenNext/Cloudflare proxy.
  **Mitigation:** kiểm tra thủ công ngay sau deploy phần 1. Nếu lỗi, api cấp cho thành viên đã đăng
  nhập một link tạm có chữ ký (hết hạn sau 1 giờ) trỏ thẳng tới domain api. Link này dùng được mà
  không cần cookie, nhưng chỉ cho đúng một file.
- **Risk 2:** api và worker không cùng thấy `/data/storage` trên Coolify. **Mitigation:** README
  ghi rõ cách mount một volume cho cả hai app. Kiểm tra sau deploy bằng cách upload ảnh rồi render
  video có ảnh đó.
- **Risk 3:** Claude trả dữ liệu sai định dạng. **Mitigation:** định dạng đầu ra cố định trong code,
  worker kiểm tra JSON, gọi lại một lần, tự sửa các lệch nhẹ, còn lại đưa qua quy tắc chặn/cảnh
  báo.
- **Risk 4:** chi phí Claude tăng không kiểm soát (không giới hạn số lần gọi). **Mitigation:** người
  dùng chấp nhận rủi ro này. Worker ghi log mỗi lời gọi Claude kèm số token, và trang Anthropic
  Console cho thấy tổng chi phí ngay từ phần 1. Ở phần 2, `/jobs` có thêm cột số lần gọi Claude của
  mỗi job (gồm cả lần gọi lại).
- **Risk 5:** ổ VPS đầy (khoảng 10–30 MB mỗi video). **Mitigation:** xóa video là xóa cứng mọi
  file. Lớp storage cho phép thêm backend R2 sau.
- **Risk 6:** MP3 có bản quyền do thành viên tự upload có thể bị tắt tiếng hoặc mất kiếm tiền.
  **Mitigation:** mặc định không có nhạc, và app gợi ý tên nhạc để chọn trong app TikTok hoặc
  Facebook khi đăng.
- **Risk 7:** FFmpeg hoặc Claude treo, hoặc worker chết giữa chừng, làm job kẹt và chặn cả hàng
  đợi. **Mitigation:** mỗi job chạy trong một tiến trình con riêng, giết được khi quá 15 phút, và
  mọi lời gọi ngoài có timeout. Khi khởi động, worker chuyển job chạy dở thành Lỗi. Coolify tự khởi
  động lại container nếu tiến trình worker chết. Không cần sửa `reels_render`: hàm `render_video`
  chạy bên trong tiến trình con.
- **Risk 8:** spec lớn, một lỗi ở phần phụ chặn luồng chính. **Mitigation:** làm hai phần, mỗi phần
  một PR. Phần 1 deploy và kiểm tra trước.

## Accepted Decisions
- Spec này gồm Claude viết kịch bản ở bản gọn: một prompt sửa được, chưa có Knowledge Base đầy đủ.
  Lý do: người dùng muốn có ngay luồng từ chủ đề đến video. Knowledge Base với ngân hàng thực phẩm
  có duyệt để spec sau. TTS và thư viện nhạc để sau nữa.
- Giữ một spec nhưng triển khai hai phần, mỗi phần một PR. Không tách thành hai spec.
- Chọn bảng job trong Postgres thay cho Redis như trong tài liệu kiến trúc. Lý do: chỉ 1–3
  video/ngày, và bớt được một dịch vụ phải chạy.
- Lưu file vào thư mục chung trên VPS (`/data/storage`), qua một lớp storage trung gian để sau này
  chuyển sang R2 không phải sửa logic nghiệp vụ. Không chọn R2 ngay để triển khai đơn giản hơn.
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
  Render lại lỗi thì video vẫn là "Xong" kèm nhãn lỗi.
- Kiểm tra trước render: chỉ chặn khi có lỗi thật, các lệch khỏi công thức kênh chỉ cảnh báo. Lý do:
  để team được làm video ngắn hoặc dài khác chuẩn.
- Tự lưu từng ô thay cho một nút Lưu cả video. Lý do: tránh người lưu sau xóa sửa của người khác.
- Định dạng đầu ra của Claude cố định trong code. Thành viên chỉ sửa phần nội dung của prompt, nên
  một lần sửa prompt không làm hỏng mọi job.
- api và worker cài gói `reels_render`, build context là gốc repo. Base Directory của app api trên
  Coolify đổi thành `/`. Lý do: ảnh xem trước và kiểm tra chữ dùng đúng code render, không chép
  code.
- Code worker nằm trong gói `reels_api` (một lệnh riêng). Lý do: chỉ có một bản model và
  migration.
- Mỗi job chạy trong một tiến trình con riêng để dừng hẳn được khi quá 15 phút, không phải sửa
  `reels_render`. Worker khởi động lại thì job chạy dở chuyển Lỗi, không tự chạy lại, để tránh gọi
  Claude ngoài ý muốn.
- `/knowledge` có hai ô prompt (viết kịch bản, nhân bản), mỗi ô có nút khôi phục mặc định riêng.
- Nhãn "MP4 chưa cập nhật" chỉ bật khi sửa thứ làm MP4 khác đi.
- Không giới hạn số lần gọi Claude. Người dùng không chọn tính năng này.

## Testing

**Unit tests:** cần — các quy tắc có giá trị biên và các phép chuẩn hóa là logic thuần. Kiểm ở
mức hàm thì nhanh và bắt được lỗi lệch một đơn vị.
- quy tắc chặn và cảnh báo, với đủ cả hai phía của mỗi biên trong Acceptance Criteria (kể cả cảnh
  tiêu đề trong tổng độ dài, cách đếm từ có `*` và `\n`);
- so khớp từ cấm (hoa thường, NFC, dấu `*`);
- kiểm tra file upload (loại, kích thước, byte đầu MP3);
- parse và chuẩn hóa đầu ra Claude: hợp lệ; JSON hỏng; thiếu tiêu đề hoặc không có cảnh; giây < 1;
  từ khóa quá dài; thiếu gợi ý nhạc; ít hơn 5 tiêu đề;
- lớp storage trên thư mục cục bộ.

**Integration tests:** cần — khóa, tranh chấp, xóa dọn file và xác thực chỉ lộ ra khi có database
thật và tiến trình thật. Render cần FFmpeg thật để chứng minh MP4 khớp CLI.
- api với Postgres thật (pytest):
  - migration `0002`;
  - tạo và sửa video, cảnh; tự lưu theo ô không đè ô khác; thành viên khác thấy và sửa được;
  - khóa khi có job; không tạo job trùng; Hủy → Đã hủy cùng kết quả của từng loại job;
  - xóa cứng dọn sạch file;
  - mọi endpoint file trả 401 khi chưa đăng nhập; kiểm tra Origin;
  - ảnh xem trước khung hình và ảnh thu nhỏ (tạo khi có ảnh tiêu đề, tạo lại khi ảnh hoặc chữ tiêu
    đề đổi);
  - lưới Pixabay và "Tìm lại ảnh": thành công, quá thời gian, sai key;
  - cờ "MP4 chưa cập nhật" (bật với chữ, giây, ảnh, thứ tự, tiêu đề, MP3, âm lượng; không bật với
    caption, hashtag, affiliate, bình luận ghim, gợi ý nhạc, từ khóa, prompt ảnh) và nhãn "Render
    lại lỗi";
  - lưu một ô khi video vừa bị khóa bị từ chối với thông báo rõ;
  - nhân bản: yêu cầu trống bị từ chối; MP3 được chép thành asset riêng; hủy rồi "Viết kịch bản"
    chạy lại job nhân bản với dữ liệu đã chụp.
- Vòng lặp worker (pytest với Postgres thật, test commit thật chứ không bọc trong transaction, và
  FFmpeg trong job CI chạy các test này):
  - nhận job tuần tự; Hủy tranh chấp với nhận job (SKIP LOCKED);
  - job quá 15 phút bị dừng thật (dùng một FFmpeg hoặc Claude giả bị treo, hạ ngưỡng thời gian
    trong test): tiến trình con và FFmpeg đều chết, job chuyển Lỗi, không ghi thêm gì, và job kế
    tiếp chạy được;
  - worker khởi động khi có job đang chạy dở: job thành Lỗi, video mở khóa, job không tự chạy lại;
  - chi tiết lỗi (stderr FFmpeg, câu trả lời thô của Claude) được lưu vào job;
  - job viết kịch bản và nhân bản với Claude giả: hợp lệ; hỏng → gọi lại → Lỗi; lệch nhẹ → lưu;
  - tự gán Pixabay giả, và Pixabay lỗi vẫn lưu kịch bản;
  - render thật bằng FFmpeg từ dữ liệu `samples/xuong-khop.json` đã nạp vào database, so với MP4
    do CLI (`python -m reels_render samples/xuong-khop.json -o <file>.mp4`) tạo trong cùng test (độ dài, kích thước, khung giữa mỗi cảnh ≤ 3/255); so khung đầu với
    ảnh xem trước cảnh tiêu đề;
  - render lỗi giữ MP4 cũ; MP3 hỏng → "File nhạc không đọc được";
  - worker chờ khi bảng `jobs` chưa có.

**E2E tests:** cần — để chứng minh luồng của người dùng chạy qua web, api và worker cùng lúc, kể
cả việc tự cập nhật trạng thái và phát MP4 trong trình duyệt.
- Claude và Pixabay giả bằng một server HTTP cục bộ. Trỏ tới nó qua biến môi trường base URL,
  không thêm cờ giả lập vào code production.
- Job `web` trong CI cài FFmpeg và chạy worker thật.
- Các luồng:
  - tạo video → sửa cảnh → Tìm lại ảnh → render → phát và tải MP4;
  - `/knowledge`: sửa prompt và từ cấm;
  - phần 2: lưới Pixabay, MP3, nhân bản, `/jobs`.
- Sửa các bài E2E hiện có bị ảnh hưởng:
  - câu kiểm tra trạng thái trống "Chưa có video nào" sau đăng nhập (`web/e2e/app.spec.ts` khoảng
    dòng 70–71);
  - bài "coming-soon pages from the menu" (khoảng dòng 82–89): bỏ `/knowledge`, bỏ `/jobs` ở phần
    2, giữ `/music`.
- `api/scripts/e2e_reset.py` dọn thêm các bảng mới.

## Verification

### Agent Verification

| Step | Expected Result |
|------|-----------------|
| 1. Chạy pytest của api (gồm các test vòng lặp worker, với Postgres và FFmpeg) và của `worker/` | Tất cả qua |
| 2. Chạy `npm run typecheck`, `npm run e2e` và build OpenNext trong `web/` | Tất cả qua |
| 3. Chạy test so khớp render: nạp `samples/xuong-khop.json` cùng ảnh vào database và storage, chạy job render, rồi so với MP4 của `python -m reels_render samples/xuong-khop.json -o <file>.mp4` | Cùng độ dài và kích thước, khung giữa mỗi cảnh chênh ≤ 3/255, khung đầu khớp ảnh xem trước tiêu đề |
| 4. Chạy local api, worker và web với Claude và Pixabay thật (nếu `.env` có key), tạo video "thực phẩm tốt cho xương khớp người sau 50 tuổi", rồi render | Kịch bản đủ các phần, MP4 9:16 tạo được, thời lượng job render ≤ 2× độ dài trên máy dev |
| 5. Build image api và image worker bằng Docker từ gốc repo | Cả hai build được. Image worker có `ffmpeg -version` ≥ 4.3 và `ffprobe` |
| 6. Đọc README phần triển khai | Có đủ các bước thủ công trên Coolify, GitHub và Cloudflare (xem User Verification) |

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
- **Thử thật trên reels.quangdang.xyz sau khi deploy phần 1:**
  - làm một video từ chủ đề đến MP4 và bấm giờ (≤ 10 phút);
  - xem thời lượng render hiện ở trang video (≤ 2× độ dài video);
  - upload một ảnh rồi render video có ảnh đó (kiểm tra volume chung);
  - phát và tua MP4 trong trình duyệt (kiểm tra Range qua Cloudflare).

  Bước này cần làm tay để kiểm tra những gì chỉ thấy trên hạ tầng thật: Cloudflare proxy, volume
  chung và tốc độ VPS.
- **Sau khi deploy phần 2:** upload MP3 và chỉnh âm lượng, rồi nghe MP4; nhân bản một video với một
  yêu cầu đổi.
