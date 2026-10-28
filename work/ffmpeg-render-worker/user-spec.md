---
# Creation date (YYYY-MM-DD)
created: 2026-10-28

# Status: draft | approved
status: draft

# Work type: feature | bug | refactoring
type: feature
---

# User-spec: ffmpeg-render-worker

> **Executor instruction.** If the project has Project Knowledge, first read its main `SKILL.md`,
> then only the materials it routes to for this task. Read `decisions.md` if it exists. Work from
> the root of the project this spec belongs to. Implement the entire user-spec. Use the execution
> skills appropriate to the work.

## What We Are Building

Lõi render video bằng Python (package `reels_render`, đặt trong thư mục `worker/`) cùng một lệnh
CLI mỏng. Đầu vào là một file JSON kịch bản gồm cảnh tiêu đề và các cảnh nội dung, kèm ảnh từng
cảnh và một file nhạc nền tùy chọn. Đầu ra là MP4 dọc 1080×1920, 30fps, H.264/AAC, đúng Video
Template của kênh. Hộp chữ được Pillow vẽ sẵn thành PNG trong suốt. Mọi thứ được ghép trong một
FFmpeg filter graph duy nhất, gồm Ken Burns, overlay chữ, crossfade và mix nhạc.

Spec này không bao gồm Redis, Postgres/RenderJob, TTS, tìm ảnh stock, Docker và giao diện web.
Các spec sau sẽ gọi vào lõi này.

## Why

Chủ kênh mất khoảng 30 phút cho mỗi video, phần lớn là dựng trong CapCut. Lõi render là phần thay
thế CapCut và là nền cho worker, UI, TTS và ảnh stock ở các spec sau. Có CLI thì kiểm tra được
template và xuất được video thật ngay, chưa cần UI.

## Expected Behavior

1. Người dùng chuẩn bị một thư mục gồm `script.json` và ảnh. Đường dẫn ảnh trong JSON tính tương
   đối theo thư mục chứa file JSON. Định dạng JSON như sau:

   ```json
   {
     "title":  { "text": "5 MÓN GIÚP\n*XƯƠNG CHẮC KHỎE*\nSAU TUỔI 50", "seconds": 3, "image": "xuong-khop/00-tieu-de.jpg" },
     "scenes": [
       { "text": "Cá nhỏ ăn cả xương\nGiàu *canxi*, rẻ, dễ tìm", "seconds": 4, "image": "xuong-khop/01-ca-nho.jpg" }
     ]
   }
   ```

   - `*...*` đánh dấu từ khóa tô đỏ.
   - `\n` là xuống dòng thủ công, ví dụ tên món ở dòng trên và lợi ích ở dòng dưới.
   - Chữ được tự in hoa khi render.
2. Người dùng chạy lệnh sau:

   ```
   python -m reels_render script.json -o out/video.mp4 [--music nhac.mp3] [--music-volume 0.25]
   ```

3. CLI kiểm tra toàn bộ đầu vào trước khi gọi FFmpeg. Nếu có lỗi, CLI in thông báo tiếng Việt nêu
   rõ chỗ lỗi ("Cảnh tiêu đề: …", "Cảnh 3: …" đánh số từ 1, hoặc đường dẫn file), thoát với mã khác
   0 và không tạo hay sửa file output.
4. Nếu đầu vào hợp lệ, hệ thống render như sau:
   - Video được ghi ra file tạm cạnh đích, tạo thư mục cha nếu chưa có.
   - Chỉ khi render thành công mới thay file đích.
   - File trung gian luôn được dọn.
   - CLI in ra đường dẫn video và thời gian render.
5. Người dùng mở MP4 và xem được ngay:
   - Khung hình đầu tiên là cảnh tiêu đề có chữ, dùng làm thumbnail.
   - Mỗi cảnh có ảnh phủ kín khung, Ken Burns zoom vào chậm.
   - Chữ nằm trong hộp vàng, các cảnh nối với nhau bằng crossfade ngắn.
   - Nhạc nền nhỏ và tắt dần ở cuối.

Lõi là một hàm Python gọi được trực tiếp (đầu vào → file MP4, lỗi có kiểu). CLI chỉ là lớp mỏng
bọc hàm này. Worker ở spec sau sẽ gọi cùng hàm này.

## Acceptance Criteria

**Output và thời lượng**
- [ ] Video output là 1080×1920, 30fps, H.264 `yuv420p`, AAC, và luôn có một audio stream.
- [ ] Tổng thời lượng video bằng tổng `seconds` của mọi cảnh, sai lệch tối đa ±1 khung hình.
      `seconds` lẻ được làm tròn về khung hình gần nhất (1/30s).
- [ ] Crossfade giữa các cảnh dài 0.4s và chia đều quanh ranh giới (0.2s mỗi bên).
- [ ] Khung đầu tiên là cảnh tiêu đề rõ nét đã có chữ, không fade-in.

**Ảnh và chuyển động**
- [ ] Ảnh không đúng 9:16 được phóng phủ kín khung rồi cắt lấy phần giữa, không có viền đen.
- [ ] Ảnh có EXIF xoay (ảnh điện thoại) hiển thị đúng chiều.
- [ ] Mọi cảnh có Ken Burns zoom vào chậm quanh tâm, từ 100% đến khoảng 112%.

**Hộp chữ**
- [ ] Hộp nền vàng (`#FFD60A`), chữ đen (`#111111`) in hoa đậm, font Be Vietnam Pro Black. Phần
      `*...*` có màu đỏ (`#E10600`). Dấu tiếng Việt, kể cả dấu chồng như Ổ hay Ặ, hiển thị đủ, không bị cắt hay dính vào dòng
      trên.
- [ ] Cảnh tiêu đề:
  - chữ nằm giữa khung, cỡ 96px;
  - tự xuống dòng và thu nhỏ dần đến tối thiểu 64px;
  - tối đa 5 dòng;
  - hộp rộng tối đa 960px.
- [ ] Cảnh nội dung:
  - chữ nằm ở 1/3 dưới khung, đáy hộp tại y = 1440;
  - cỡ 84px, tự xuống dòng và thu nhỏ đến tối thiểu 60px;
  - tối đa 3 dòng;
  - hộp rộng tối đa 960px.

**Nhạc**
- [ ] Khi có `--music`:
  - nhạc ngắn hơn video thì lặp lại, nhạc dài hơn thì bị cắt;
  - âm lượng mặc định 0.25 (khoảng −12 dB);
  - `--music-volume` nhận giá trị từ 0 đến 1;
  - nhạc fade-out 1.5s ở cuối video.
- [ ] Khi không có `--music`, video vẫn có một track âm thanh im lặng dài đủ thời lượng.

**Lỗi đầu vào** (báo lỗi tiếng Việt, nêu cảnh hoặc file, thoát mã khác 0, không đụng tới file output)
- [ ] Lỗi file và cấu trúc:
  - JSON hỏng cú pháp, thiếu trường, hoặc không có cảnh nội dung;
  - thiếu ảnh, file ảnh không tồn tại, hoặc ảnh hỏng;
  - file nhạc không tồn tại;
  - `--music-volume` nằm ngoài khoảng 0–1.
- [ ] Lỗi nội dung cảnh:
  - `seconds` nhỏ hơn 1;
  - text rỗng hoặc chỉ có khoảng trắng;
  - có dòng trống do `\n\n`;
  - có `**` rỗng hoặc dấu `*` không đóng cặp;
  - chữ không vừa hộp ở cỡ tối thiểu, hoặc vượt số dòng tối đa.
- [ ] Không tìm thấy `ffmpeg` hoặc `ffprobe` thì báo lỗi kèm hướng dẫn cài đặt.

**Ghi file output**
- [ ] FFmpeg chạy lỗi: báo lỗi kèm phần cuối stderr, xóa file tạm và file trung gian. Video cũ cùng
      tên, nếu có, giữ nguyên.
- [ ] Render xong nhưng không thay được file đích (ví dụ file đang mở trong trình phát trên
      Windows): giữ bản mới với tên `<tên>.new.mp4` cạnh file đích, báo đường dẫn bản mới, thoát
      mã khác 0. Nếu tên đó cũng đã có và bị khóa thì thử lần lượt `<tên>.new-2.mp4`,
      `<tên>.new-3.mp4`… và lấy tên đầu tiên ghi được. Bản render không bao giờ bị mất.
- [ ] Render thành công thì CLI in ra đường dẫn video và thời gian render, thoát mã 0.
- [ ] Sau một lần render thành công, không còn sót file tạm hay file trung gian nào.

**Tốc độ và dữ liệu mẫu**
- [ ] Trên máy dev (i7-8700), tốc độ render không chậm hơn tỉ lệ 60s cho mỗi 30s video. Đo bằng
      render `xuong-khop`.
- [ ] `samples/xuong-khop.json` được chuyển sang định dạng mới:
  - bỏ emoji, outro và disclaimer;
  - đổi `**...**` thành `*...*`;
  - đi kèm 6 ảnh trong `samples/xuong-khop/` (1 ảnh tiêu đề và 5 món) do người dùng cung cấp. Ảnh
    được **commit vào repo** (khoảng 300–500 KB mỗi ảnh) để ai clone về cũng render thử được ngay;
  - render thành công bằng lệnh CLI ở trên.

## Constraints

- **Công nghệ:**
  - Python 3.12, Pillow và FFmpeg gọi qua subprocess.
  - Không dùng MoviePy hay Remotion (architecture.md).
  - Mọi thứ ghép trong một filter graph duy nhất.
- **Chạy trên cả Windows và Linux:**
  - Hiện tại phát triển và chạy native trên Windows, với Python và FFmpeg cài qua winget.
  - Spec sau sẽ chạy cùng code này trong image worker Linux. Image đó chưa được chọn, nên chưa biết
    phiên bản FFmpeg. Vì vậy chỉ dùng tính năng FFmpeg có từ bản 4.3 trở lên, không viết nhánh code
    riêng theo phiên bản. Filter graph luôn truyền qua đối số `-filter_complex`, không đọc từ file:
    với 6–8 cảnh, cả lệnh chỉ dài vài KB, còn xa giới hạn dòng lệnh của Windows.
  - Dùng `pathlib` cho mọi đường dẫn.
  - Đọc JSON bằng `encoding="utf-8"`.
  - Chuẩn hóa văn bản về NFC.
- **An toàn khi gọi FFmpeg:**
  - Không đặt đường dẫn file bên trong filter graph. Mọi file đều truyền qua `-i` và tham chiếu
    bằng nhãn stream.
  - Gọi subprocess dạng danh sách đối số, không qua shell. Đường dẫn repo có dấu cách và đường dẫn
    đến từ JSON.
- **Font:** `BeVietnamPro-Black.ttf` và `OFL.txt` được commit trong repo. Code nạp font theo đường
  dẫn tương đối với package, không theo thư mục làm việc.
- **Hiệu năng:** render không chậm hơn tỉ lệ 30s video ≤ 60s trên i7-8700.
- **Kiến trúc:**
  - Lõi là hàm gọi được, ném lỗi có kiểu, để worker sau dùng và ghi lỗi vào RenderJob.
  - Phần mix audio để ngỏ cho track TTS sau này.
- **Phạm vi và repo:**
  - Không lưu trữ gì ngoài file MP4 output.
  - Thêm `.venv/` và `.pytest_cache/` vào `.gitignore`.

## Risks

- **zoompan bị rung**, do tọa độ crop bị làm tròn. **Mitigation:** phóng ảnh lớn hơn khung trước
  khi zoompan, cân chỉnh mức phóng sao cho vẫn giữ ngân sách 30s ≤ 60s. Dùng `on` (chỉ số khung)
  để zoom tuyến tính. Với ảnh đơn khung, `d` bằng số khung của cảnh.
- **Dấu tiếng Việt chồng bị cắt hoặc sát dòng trên.** **Mitigation:** tính chiều cao dòng từ
  `font.getmetrics()` thay vì bbox từng dòng, chuẩn hóa NFC. Có test Pillow cho phần này, và người
  dùng xem tận mắt.
- **FFmpeg trên Windows khác FFmpeg trong image Linux sau này.** winget hiện cài Gyan.FFmpeg bản
  9.x, còn image Linux chưa được chọn. **Mitigation:** chỉ dùng các filter và tùy chọn ổn định có từ
  bản 4.3 (`zoompan`, `xfade`, `overlay`, `afade`, `-stream_loop`), truyền graph qua
  `-filter_complex`, và chạy smoke test lại khi dựng image worker.
- **Lệch offset xfade làm sai tổng thời lượng.** **Mitigation:** tính timeline ở một module thuần
  có unit test, và snap mọi mốc về khung hình.
- **Ảnh điện thoại bị xoay** vì FFmpeg bỏ qua EXIF. **Mitigation:** chuẩn hóa ảnh bằng
  `ImageOps.exif_transpose` thành file trung gian trước khi đưa vào FFmpeg.
- **Alias Python của Microsoft Store che mất python vừa cài.** **Mitigation:** hướng dẫn tắt alias
  trong "App execution aliases" hoặc gọi trực tiếp đường dẫn python vừa cài.

## Accepted Decisions

- Chọn làm lõi render và CLI trước, thay vì worker đầy đủ có Redis, Postgres và Docker, vì repo
  chưa có code nào. Queue, DB, TTS, ảnh stock và Docker là các spec sau, sẽ gắn vào lõi này.
- Chọn định dạng JSON theo mô hình dữ liệu trong tài liệu (cảnh tiêu đề và các cảnh, mỗi cảnh có
  `text`/`seconds`/`image`, `*đỏ*`) thay vì định dạng prototype Remotion (hook, outro, emoji,
  disclaimer). Disclaimer vẫn đang hoãn theo content.md.
- Mỗi cảnh chỉ có một trường `text`, dùng `\n` để tách tên món và dòng lợi ích, không có huy hiệu
  số thứ tự. Cách này khớp mô hình dữ liệu và đơn giản hơn so với hai trường riêng.
- Cảnh thiếu ảnh thì báo lỗi thay vì dùng nền tạm, để không bao giờ ra video kém chất lượng. Tìm
  ảnh stock sẽ là spec sau.
- Cảnh tiêu đề có ảnh riêng bắt buộc, không mượn ảnh của cảnh 1.
- Hộp chữ có một kiểu cố định là nền vàng chữ đen. Phương án "chữ vàng viền đen" và phương án cho
  cấu hình đều bị loại vì khó đọc trên ảnh sáng, còn cấu hình thì chưa cần.
- Chữ cảnh nội dung đặt ở 1/3 dưới, đáy hộp tại y = 1440, để không che món ăn và tránh vùng
  caption/nút của Reels/TikTok.
- Hình học hộp chữ theo bộ số đề xuất: rộng 960px; tiêu đề 96 → 64px, tối đa 5 dòng; nội dung
  84 → 60px, tối đa 3 dòng. Phương án chữ to hơn, ít dòng hơn bị loại vì kịch bản dài sẽ bị báo
  lỗi nhiều.
- Chữ dài thì tự xuống dòng và thu nhỏ, chỉ báo lỗi khi vẫn không vừa. Phương án báo lỗi ngay khi
  vượt số chữ bị loại.
- Crossfade 0.4s đặt giữa ranh giới hai cảnh, tổng thời lượng bằng tổng `seconds`. Cảnh ở giữa
  hiện rõ `seconds − 0.4s`, cảnh đầu và cảnh cuối hiện rõ `seconds − 0.2s`. Phương án cộng thêm
  thời gian ngoài `seconds` (làm video dài hơn) bị loại.
- `seconds` phải ≥ 1 và được làm tròn theo khung hình, thay vì ép khoảng 3–5s của template. Cách
  này giữ smoke test nhanh và để người viết kịch bản tự chọn nhịp.
- Ken Burns luôn zoom vào, không xen kẽ vào và ra.
- Nhạc là tùy chọn qua `--music`, âm lượng `--music-volume` mặc định 0.25 và cũng là tham số của
  hàm render. Nhạc ngắn thì lặp. Không có nhạc thì vẫn có track im lặng, vì nền tảng xử lý tốt hơn
  và track TTS sau này sẽ mix vào đó.
- Output 1080×1920 ở 30fps, thay vì 720×1280.
- Font Be Vietnam Pro Black được đóng gói trong repo (giấy phép OFL), không cài trên từng máy.
- Ghi output an toàn: render ra file tạm rồi mới thay file đích, tự tạo thư mục, luôn dọn file
  trung gian. Nếu file đích đang bị khóa thì giữ bản mới `<tên>.new.mp4` và báo lỗi. Nếu tên đó
  cũng bị khóa thì đánh số tiếp (`.new-2`, `.new-3`…) thay vì ghi đè hoặc để lại file tạm.
- Commit 6 ảnh mẫu vào repo thay vì chỉ để JSON, để ai clone về cũng render thử được ngay.
- Thông báo lỗi viết bằng tiếng Việt và đánh số cảnh từ 1, đúng quy ước giao diện chỉ tiếng Việt
  và sẵn sàng hiển thị ở Job log sau này.
- Ảnh không đúng 9:16 thì cắt phần giữa cho phủ kín khung, thay vì dùng nền mờ với ảnh nguyên.
- Phát triển với Python và FFmpeg cài trực tiếp trên Windows qua winget. Agent sẽ chạy lệnh cài và
  người dùng duyệt lệnh. Docker để lại cho spec sau.

## Testing

**Unit tests:** cần thiết, chạy bằng pytest và không cần FFmpeg. Các phần cần cover:

- Validation và thông báo lỗi tiếng Việt cho từng lỗi đầu vào ở Acceptance Criteria, kiểm tra đúng
  "Cảnh tiêu đề", "Cảnh N" hoặc đường dẫn được nêu. Trường hợp không tìm thấy ffmpeg/ffprobe được
  giả lập.
- Parser `*đỏ*`, bao gồm dấu `*` lẻ và `**` rỗng.
- In hoa tiếng Việt và chuẩn hóa NFC.
- Ngắt dòng và thu nhỏ chữ, với các ngưỡng:
  - chữ vừa ở 84px;
  - chữ phải thu nhỏ mới vừa;
  - chữ không vừa ở 60px hoặc quá 3 dòng thì lỗi;
  - tiêu đề quá 5 dòng thì lỗi.
- Timeline:
  - làm tròn theo khung hình;
  - offset xfade chia đều quanh ranh giới;
  - tổng thời lượng bằng tổng `seconds`.
- Builder filter graph cho cả nhánh có nhạc và không có nhạc, kiểm tra không có đường dẫn file nào
  nằm trong graph.
- Chuẩn hóa ảnh EXIF: ảnh gắn orientation = 6 phải ra ảnh trung gian đã xoay đúng kích thước.

Lý do: đây là phần logic thuần, dễ sai, và test chạy nhanh.

**Integration tests:** cần thiết, gồm hai tầng.

- **Tầng Pillow:** PNG hộp chữ phải là RGBA, trong suốt ở ngoài hộp, có pixel vàng trong hộp, có
  pixel đỏ khi có markup, và không vượt 960px.
- **Tầng smoke render bằng FFmpeg** (skip kèm lý do nếu máy không có ffmpeg). Dùng ảnh do Pillow
  sinh ra, có cả ảnh ngang lẫn ảnh vuông, 2–3 cảnh ngắn, rồi kiểm tra bằng `ffprobe`:
  - Thông số: 1080×1920, 30fps, h264/yuv420p, thời lượng ±1 khung hình, luôn có audio stream.
  - Nhạc (tone sinh bằng FFmpeg `sine`, đo mức bằng `volumedetect`/`astats` trên từng đoạn):
    - nhạc 1s trong video 3s thì đoạn sau mốc hết nhạc gốc vẫn có tín hiệu (phân biệt được lặp
      với đệm im lặng);
    - nhạc dài thì bị cắt;
    - mean volume đoạn giữa xấp xỉ tone gốc −12 dB (±1.5 dB), và khoảng −6 dB khi `--music-volume 0.5`;
    - 0.2s cuối nhỏ hơn đoạn giữa ít nhất 20 dB;
    - không có nhạc thì có track im lặng đủ dài.
  - Ghi file:
    - render thành công thì không còn file tạm hay file trung gian;
    - ép FFmpeg lỗi khi đã có output cũ thì output cũ còn nguyên, không sót file tạm;
    - giả lập file đích bị khóa (monkeypatch `os.replace` ném `PermissionError`) thì phải còn
      `<tên>.new.mp4` và file cũ nguyên vẹn;
    - giả lập cả file đích lẫn `<tên>.new.mp4` bị khóa thì phải ra `<tên>.new-2.mp4` và không sót file tạm.
  - CLI chạy qua subprocess:
    - thiếu ảnh thì mã thoát khác 0, có thông báo nêu cảnh và không có file output;
    - thư mục `-o` chưa có thì được tạo;
    - thành công thì mã thoát 0, stdout chứa đường dẫn video và thời gian render.

Lý do: đây là tầng duy nhất bắt được lỗi ghép graph và lỗi âm thanh (patterns.md: render smoke test).

**E2E tests:** không cần. Không có UI, và CLI đã được test qua subprocess.

## Verification

### Agent Verification

| Step | Expected Result |
|------|-----------------|
| 1. Cài Python 3.12 và FFmpeg qua winget (người dùng duyệt lệnh), tạo `.venv`, cài package | `python --version` báo 3.12. `ffmpeg -filters` có `zoompan`, `xfade`, `overlay`, `afade` |
| 2. Chạy `pytest` trong `worker/` | Toàn bộ unit, Pillow và smoke test pass, không có test nào bị skip vì thiếu ffmpeg |
| 3. Render `samples/xuong-khop.json` bằng CLI ra `out/xuong-khop.mp4`, một lần không có `--music` và một lần có `--music`. File nhạc là file người dùng cung cấp, hoặc nếu không có thì là tone thử do agent sinh bằng FFmpeg `sine` vào `out/` (không commit) | Mã thoát 0, in đường dẫn và thời gian render, file tồn tại, không sót file tạm |
| 4. Chạy `ffprobe` trên file vừa render | 1080×1920, 30fps, h264/yuv420p, có audio, thời lượng bằng tổng `seconds` ±1 khung hình |
| 5. Đo thời gian render ở bước 3 | Thời gian render ≤ 2 × thời lượng video |
| 6. Trích khung đầu và một khung giữa mỗi cảnh ra PNG để người dùng xem | Có file PNG tương ứng (agent không tự đánh giá thẩm mỹ) |

### User Verification
- Xem `out/xuong-khop.mp4` (bản có nhạc nếu bạn cung cấp file nhạc) so với Video Template:
  - khung đầu là thumbnail rõ chữ;
  - hộp vàng chữ đen in hoa, từ khóa đỏ;
  - dấu tiếng Việt đủ và không bị cắt;
  - chữ cảnh nội dung ở 1/3 dưới, không bị caption/nút che;
  - Ken Burns mượt, không rung;
  - crossfade mềm;
  - nhạc nhỏ và tắt dần ở cuối.

  Phần này cần người xem vì agent không đánh giá được chất lượng hình ảnh (patterns.md).
- Cung cấp 6 ảnh món ăn (~300–500 KB/ảnh) có quyền sử dụng rõ ràng vào `samples/xuong-khop/` trước
  bước render mẫu.
