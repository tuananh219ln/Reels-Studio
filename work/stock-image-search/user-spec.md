---
# Creation date (YYYY-MM-DD)
created: 2026-10-28

# Status: draft | approved
status: draft

# Work type: feature | bug | refactoring
type: feature
---

# User-spec: stock-image-search

> **Executor instruction.** If the project has Project Knowledge, first read its main `SKILL.md`,
> then only the materials it routes to for this task. Read `decisions.md` if it exists. Work from
> the root of the project this spec belongs to. Implement the entire user-spec. Use the execution
> skills appropriate to the work.

## What We Are Building

Bổ sung cho lõi render `reels_render` (thư mục `worker/`) khả năng tự tìm ảnh stock. Mỗi cảnh
trong kịch bản JSON (cả cảnh tiêu đề) có thể có trường `keywords`: danh sách từ khóa tiếng Việt,
sắp từ cụ thể đến chung. Cảnh nội dung không có `keywords` thì dùng dòng chữ đầu tiên của cảnh
(thường là tên món) làm từ khóa. Khi render, cảnh nào chưa có ảnh của người dùng sẽ được tự tìm
ảnh chụp thật trên Pixabay bằng tiếng Việt (`lang=vi`), rồi tải về và dùng cho lần render đó.

Ảnh tìm tự động được chọn ngẫu nhiên mỗi lần render để video đa dạng, và không ghi vào JSON. Nếu
một cảnh không tìm được ảnh dùng được, CLI hỏi ngay trong terminal để người dùng kéo thả ảnh vào.
Ảnh đó được chép cạnh kịch bản, ghi vào trường `image`, rồi render chạy tiếp.

## Why

Hiện tại người dùng phải tự tìm, tải, đặt tên và ghi đường dẫn ảnh cho từng cảnh thì mới render
được. Với tính năng này, một kịch bản chỉ có chữ, thời lượng và từ khóa là ra video có ảnh thật
đúng chủ đề ngay. Render lại thường cho bộ ảnh khác, nên làm nhiều video cùng chủ đề không bị lặp
ảnh. Những món kho ảnh nước ngoài không có (món đặc trưng Việt Nam) thì người dùng bổ sung ảnh
ngay trong lúc chạy, không phải sửa file rồi chạy lại.

## Expected Behavior

1. Người dùng viết kịch bản như hiện nay. Mỗi cảnh có thể bỏ trống `image` và thêm `keywords`:

   ```json
   {
     "title":  { "text": "5 MÓN GIÚP\n*XƯƠNG CHẮC KHỎE*\nSAU TUỔI 50", "seconds": 3,
                 "keywords": ["cá nhỏ chiên giòn", "sữa chua", "món ăn giàu canxi"] },
     "scenes": [
       { "text": "Cá nhỏ ăn cả xương\nGiàu *canxi*", "seconds": 4,
         "keywords": ["cá kho tộ", "cá kho", "món cá"] },
       { "text": "Vừng đen\nRắc vào *cháo*", "seconds": 4 },
       { "text": "Sữa chua\nBổ sung *canxi*", "seconds": 4, "image": "xuong-khop/02-sua-chua.jpg" }
     ]
   }
   ```

2. Người dùng chạy lệnh render như cũ:
   `python -m reels_render script.json -o out/video.mp4`.
3. Với từng cảnh, tool quyết định nguồn ảnh như sau:
   - Có `image` trỏ tới file tồn tại: luôn dùng ảnh đó, không tìm.
   - `image` trống hoặc không có: tìm theo `keywords`. Cảnh nội dung không có `keywords` thì tìm
     theo dòng chữ đầu tiên của cảnh (ví dụ "Vừng đen"). Cảnh tiêu đề không có `keywords` thì không
     tìm (dòng đầu như "5 MÓN GIÚP" không phải tên món) mà chuyển sang hỏi người dùng.
   - `image` trỏ tới file không tồn tại: in cảnh báo (ví dụ
     `Cảnh 2: không thấy file anh-ca.jpg, sẽ tìm ảnh thay thế`) rồi tìm như trường hợp trên.
4. Tool tìm cho mọi cảnh cần tìm. Tool thử từng từ khóa theo thứ tự trên Pixabay, và chỉ sang
   từ khóa tiếp theo khi từ khóa hiện tại không cho ảnh dùng được. Kết quả giữ đúng thứ tự liên quan
   Pixabay trả về. Tool chọn ngẫu nhiên trong 3 ảnh đầu chưa dùng cho cảnh khác trong cùng video
   (ảnh dọc, ngang hay vuông đều được). Ảnh được tải về thư mục tạm.
5. Cảnh không có ảnh dùng được sau khi thử hết từ khóa (hoặc cảnh tiêu đề không có `keywords`):
   - Chạy trong terminal (stdin của CLI là terminal, `sys.stdin.isatty()`): sau khi đã tìm xong
     mọi cảnh, CLI hỏi lần lượt từng cảnh, ví dụ
     `Cảnh 3 (CÁ KHO TỘ) chưa có ảnh. Kéo thả ảnh vào đây rồi nhấn Enter:`.
   - Người dùng kéo thả ảnh. Tool chép ảnh vào thư mục con mang tên kịch bản, ghi vào `image`
     trong JSON và render tiếp.
   - Không có terminal (stdin bị pipe hoặc chuyển hướng, worker sau này gọi thẳng
     `render_video`): lỗi có kiểu liệt kê các cảnh thiếu ảnh, không chạy FFmpeg.
6. Khi render xong, CLI in đường dẫn video và hai thời gian riêng, kèm số lượt gọi API tìm kiếm,
   ví dụ `Tìm ảnh: 8.2s (4 lượt gọi API) · Render: 15.1s`. Khi không cảnh nào cần tìm thì dòng
   này ghi `Tìm ảnh: 0.0s (0 lượt gọi API)`.
7. Render lại cùng kịch bản thường cho bộ ảnh tự động khác. Ảnh người dùng đã nhập vẫn giữ
   nguyên.

## Acceptance Criteria

**Kịch bản**
- [ ] Cảnh tiêu đề và cảnh nội dung nhận trường tùy chọn `keywords`: danh sách chuỗi, mỗi chuỗi
      không rỗng (sau khi bỏ khoảng trắng hai đầu) và tối đa 100 ký tự. Từ khóa viết tiếng Việt,
      và mọi lần tìm gửi `lang=vi` cho Pixabay. Tool không kiểm tra ngôn ngữ của từ khóa.
      `keywords: []` được coi như không có `keywords`.
- [ ] Cảnh nội dung không có `keywords` dùng một từ khóa duy nhất: dòng chữ đầu tiên của cảnh, bỏ
      dấu `*`, giữ nguyên dấu tiếng Việt, cắt còn tối đa 100 ký tự. Cảnh tiêu đề không có
      `keywords` thì không tìm, mà được coi là không có ảnh dùng được (CLI hỏi người dùng).
- [ ] `keywords` sai kiểu (không phải danh sách, phần tử không phải chuỗi, chuỗi rỗng, dài quá 100
      ký tự) báo lỗi tiếng Việt nêu đúng cảnh ngay khi đọc kịch bản, trước khi tìm ảnh.
- [ ] `image` trở thành tùy chọn. `image` rỗng hoặc vắng mặt không còn là lỗi.
- [ ] `samples/xuong-khop.json` được bổ sung `keywords` tiếng Việt cho cả 6 cảnh. Các ảnh mẫu hiện có vẫn
      được dùng.

**Chọn và tìm ảnh**
- [ ] Cảnh có `image` trỏ tới file tồn tại luôn dùng ảnh đó và không gửi yêu cầu tìm kiếm nào.
- [ ] Cảnh có `image` trỏ tới file không tồn tại thì in cảnh báo nêu cảnh và tên file, rồi tìm ảnh
      thay thế (theo `keywords`, hoặc dòng chữ đầu với cảnh nội dung không có `keywords`). Cảnh
      tiêu đề không có `keywords` thì cảnh báo ghi "không thấy file …" và cảnh đó được hỏi người
      dùng như cảnh không có ảnh dùng được.
- [ ] Từ khóa được thử theo đúng thứ tự trong danh sách. Mỗi từ khóa chỉ có một lần tìm trên
      Pixabay (không tính 1 lần thử lại khi lỗi tạm, và không gọi API nếu từ khóa đã có trong
      cache). Pixabay là nguồn ảnh duy nhất.
- [ ] Chỉ lấy ảnh chụp và luôn bật lọc ảnh nhạy cảm (Pixabay `image_type=photo`,
      `safesearch=true`). Ứng viên là 10 kết quả đầu của mỗi lần
      tìm, giữ thứ tự liên quan của Pixabay. Tool bỏ các ứng viên đã dùng cho cảnh khác trong cùng
      video, rồi chọn ngẫu nhiên trong 3 ứng viên đầu còn lại. Không ưu tiên hay loại ảnh theo
      hướng: ảnh ngang và vuông được lõi render cắt phần giữa như hiện nay. Không loại ảnh vì kích
      thước nhỏ. Ứng viên được chọn mà không dùng được (hỏng, quá cỡ, tải lỗi) thì bỏ và chọn lại
      theo cùng quy tắc trong các ứng viên còn lại.
- [ ] Ảnh tải bản `largeImageURL` của Pixabay.
- [ ] Không lưu lịch sử lựa chọn giữa các lần render.
- [ ] Hai cảnh trong cùng video không dùng chung một ảnh tự động. Nếu không còn ảnh mới, cảnh sau
      thử từ khóa tiếp theo. Thử hết vẫn không có ảnh mới thì dùng lại ảnh trùng, không hỏi
      người dùng.
- [ ] Ảnh tự động được tải vào thư mục tạm của lần render và xóa sau khi render. Không ghi ảnh
      tự động vào JSON hay vào repo.
- [ ] Kết quả tìm kiếm (danh sách ảnh của mỗi từ khóa) được lưu 24 giờ trong thư mục
      `<thư mục tạm của máy>/reels_render_cache/`. Trong 24 giờ đó, cùng từ khóa không gọi lại
      API mà chọn từ danh sách đã lưu theo đúng quy tắc chọn ảnh ở trên (3 ứng viên đầu chưa
      dùng). Quá 24 giờ thì gọi lại.
- [ ] File cache được ghi nguyên tử. File cache hỏng hoặc đọc không được thì coi như chưa có cache
      (gọi API lại). Không ghi được cache thì bỏ qua và render vẫn tiếp tục. Lỗi cache không bao
      giờ làm dừng render hay in traceback.
- [ ] Ứng viên quá 15 MB, không phải ảnh hoặc ảnh hỏng bị bỏ qua, và tool lấy ứng viên khác. Hết
      10 ứng viên của một từ khóa thì coi như từ khóa đó không có kết quả.
- [ ] Kịch bản mà mọi cảnh đều có ảnh hợp lệ thì render được khi không có key và không có mạng,
      không gửi yêu cầu nào.

**Hỏi người dùng (CLI)**
- [ ] CLI chỉ hỏi sau khi đã tìm xong mọi cảnh cần tìm, rồi hỏi lần lượt từng cảnh còn thiếu ảnh.
      Lời hỏi nêu "Cảnh tiêu đề" hoặc "Cảnh N" kèm dòng chữ đầu tiên của cảnh.
- [ ] Đường dẫn kéo thả từ cmd, PowerShell hoặc Windows Terminal được nhận đúng, kể cả khi có dấu
      cách, có dấu nháy `"..."`/`'...'` hoặc có tiền tố `& '...'`.
- [ ] Đường dẫn sai, không phải ảnh hoặc dòng trống: báo lỗi tiếng Việt và hỏi lại cảnh đó.
- [ ] Ảnh nhập được chép vào thư mục con mang tên kịch bản, cạnh file JSON (ví dụ
      `samples/xuong-khop/03-ca-kho-to.jpg`). Tên file là số thứ tự cảnh (`00` cho cảnh tiêu đề)
      cộng dòng chữ đầu của cảnh viết thường, không dấu, nối bằng `-`, giữ đuôi file gốc. Nếu tên
      đã có thì thêm `-2`, `-3`…, không bao giờ ghi đè.
- [ ] Sau mỗi ảnh nhập, `image` của cảnh đó được ghi vào JSON (đường dẫn tương đối, dấu `/`). File
      được ghi nguyên tử, UTF-8, giữ nguyên tiếng Việt, thụt lề đều. Các trường khác không đổi
      giá trị.
- [ ] Ctrl+C hoặc hết dữ liệu nhập (EOF) khi đang hỏi: dừng, không render, thoát mã khác 0. Các ảnh
      đã nhập trước đó vẫn nằm trong JSON và lần sau không bị hỏi lại.
- [ ] Sau khi nhập đủ ảnh, render chạy tiếp trong cùng lệnh, không phải chạy lại.
- [ ] Lõi (`render_video`) không bao giờ đọc bàn phím. Khi thiếu ảnh mà không có ai để hỏi, lõi
      ném lỗi có kiểu (lớp con của `RenderError`) liệt kê các cảnh thiếu ảnh, và FFmpeg không
      chạy.

**Lỗi**
- [ ] `PIXABAY_API_KEY` trống hoặc vắng mà có cảnh cần tìm: dừng ngay với lỗi có kiểu, hướng dẫn
      đặt key vào `.env`, không hỏi người dùng.
- [ ] Không có mạng khi cần tìm: dừng với lỗi có kiểu, không hỏi người dùng. Không có bước dò
      mạng riêng; "không có mạng" là yêu cầu tìm đầu tiên lỗi ở mức kết nối (DNS, từ chối kết nối,
      lỗi SSL). Lỗi kết nối được xử lý như hết thời gian chờ: đợi 5 giây, thử lại 1 lần, rồi dừng.
- [ ] Việc kiểm tra key và mạng chỉ áp dụng khi có ít nhất một cảnh cần tìm (cảnh nội dung thiếu
      ảnh, hoặc cảnh tiêu đề thiếu ảnh có `keywords`).
      Tìm ảnh luôn chạy xong trước mọi lời hỏi, nên kịch bản trộn mà thiếu key hoặc mất mạng sẽ
      dừng trước khi hỏi và JSON không bị sửa.
- [ ] Pixabay trả 429, lỗi 5xx hoặc hết thời gian chờ (15 giây mỗi yêu cầu): đợi 5 giây, thử lại
      1 lần. Vẫn lỗi thì dừng với lỗi có kiểu (ví dụ "Pixabay đang giới hạn lượt tìm, thử lại sau
      1 phút"), không hỏi người dùng.
- [ ] Pixabay báo key sai hoặc bị thu hồi: dừng ngay với thông báo "Key Pixabay không hợp lệ, kiểm
      tra file .env". Dấu hiệu nhận biết (đã gọi thử trong lúc lập spec): HTTP 400 với nội dung chứa
      `API key`, ví dụ `[ERROR 400] Invalid API key...` hoặc
      `[ERROR 400] Invalid or missing API key...`. Phản hồi 400 khác (ví dụ
      `[ERROR 400] "per_page" is out of valid range.`) không được báo là lỗi key.
- [ ] Pixabay từ chối một từ khóa vì lý do khác (lỗi 4xx khác 429, không phải lỗi key): bỏ qua từ
      khóa đó, in cảnh báo, tiếp tục.
- [ ] Tải ảnh lỗi mạng (403, timeout, mất kết nối): thử ứng viên khác. Mỗi lần tải ảnh tối đa
      15 giây (tính cả thời gian nhận dữ liệu, không chỉ thời gian chờ kết nối). Mỗi cảnh tối đa
      2 lần tải lỗi mạng; đến lần thứ 2 thì dừng với lỗi có kiểu ("Mạng chậm hoặc bị chặn khi tải
      ảnh, thử lại sau"), không hỏi.
- [ ] Cảnh đã gặp bất kỳ lỗi mạng nào (khi tìm hoặc khi tải) thì không bao giờ chuyển sang hỏi
      người dùng, kể cả khi các từ khóa khác không có kết quả: hoặc lấy được ảnh từ ứng viên khác,
      hoặc dừng với lỗi có kiểu ("Không tải được ảnh cho Cảnh N do lỗi mạng, thử lại sau"). Chỉ
      cảnh không có ảnh dùng được và không gặp lỗi mạng nào mới được hỏi. Ở quy tắc này, "lỗi
      mạng" là lần tải ảnh thất bại vì mạng, hoặc lần tìm vẫn lỗi sau khi đã thử lại. Lần tìm lỗi
      nhưng thử lại thành công thì không tính. Lỗi được tính cho cảnh đang tìm hoặc tải lúc lỗi
      xảy ra; kết quả lấy từ cache không mang theo lỗi.
- [ ] Không thông báo lỗi hay cảnh báo nào chứa giá trị API key (kể cả URL Pixabay có `key=`).
- [ ] Mọi lỗi tìm ảnh là lỗi có kiểu với thông báo tiếng Việt. CLI in thông báo và thoát mã khác
      0, không in traceback Python.

**Cấu hình và thời gian**
- [ ] Key đọc từ biến môi trường, hoặc từ file `.env` ở thư mục gốc repo (UTF-8, chấp nhận BOM,
      dấu nháy, dòng `#`, tiền tố `export`). Biến môi trường thật được ưu tiên hơn `.env`, kể cả
      khi được đặt thành chuỗi rỗng (đặt `PIXABAY_API_KEY=` trong môi trường là tắt key trong
      `.env`).
- [ ] `.env.example` liệt kê `PIXABAY_API_KEY=` với giá trị trống.
- [ ] Mọi yêu cầu HTTP gửi User-Agent riêng của tool.
- [ ] CLI in riêng thời gian tìm ảnh (kèm số lượt gọi API tìm kiếm thực sự gửi đi, tính cả lần
      thử lại, không tính tải ảnh và cache) và thời gian render. Thời gian chờ người dùng
      nhập ảnh ở lời hỏi không tính vào số nào trong hai số này. Ngân
      sách render (≤ 2× thời lượng video) chỉ áp dụng cho phần render.

**Tài liệu dự án**
- [ ] Project Knowledge được cập nhật cho khớp hành vi mới:
  - `architecture.md`: thiếu ảnh không còn là lỗi; có `keywords`; không lưu nguồn ảnh; Pixabay là
    nguồn ảnh stock duy nhất (bỏ Pexels khỏi bảng tích hợp).
  - `content.md`: từ khóa tìm ảnh là trường `keywords` tiếng Việt riêng (mặc định là dòng chữ đầu
    của cảnh).
  - `patterns.md`: nguồn ảnh stock cố định là Pixabay, không cấu hình được.
  - `deployment.md`: `PIXABAY_API_KEY` là biến đang dùng, đọc từ `.env`; bỏ `PEXELS_API_KEY`.

## Constraints

- **Không thêm thư viện:** HTTP dùng `urllib` của Python, `.env` đọc bằng parser tự viết. Không
  thêm requests, httpx hay python-dotenv.
- **Validation trước FFmpeg:** việc tìm, tải và hỏi ảnh phải xong trước khi gọi FFmpeg. Quy tắc
  ghi output an toàn hiện có giữ nguyên.
- **Điều khoản nguồn ảnh:** Pixabay yêu cầu tải ảnh về (không hotlink) và lưu kết quả tìm kiếm
  24 giờ. Không dùng Google Images vì bản quyền và vì không có cách tải tự động hợp lệ.
- **Bảo mật:** key không vào git, log hay thông báo lỗi. `.env` đã có trong `.gitignore`. Tên file
  tải về do tool đặt, không lấy từ mạng. Mỗi ảnh tải về tối đa 15 MB và phải mở được bằng Pillow.
- **Nền tảng:** chạy trên Windows (native) và Linux (worker sau này). Dùng `pathlib` cho đường
  dẫn.
- **Lõi gọi được từ worker:** phần tìm ảnh nằm trong lõi. Phần hỏi người dùng chỉ nằm ở CLI.
- **Thời gian:** việc tìm và tải ảnh thường thêm khoảng 5–15 giây mỗi lần render, người dùng chấp
  nhận.

## Risks

- **Kho ảnh nước ngoài thiếu món Việt** (cá kho tộ, vừng đen rắc cháo…). **Mitigation:** từ khóa
  từ cụ thể đến chung. Không có ảnh thì CLI hỏi người dùng, và ảnh được giữ trong JSON cho lần
  sau.
- **Tìm tiếng Việt ra ảnh lạc chủ đề:** cụm từ chung chung hoặc từ nhiều nghĩa cho ảnh sai (đã
  thử: "thực phẩm tốt cho xương" ra cây xương rồng, "đậu phụ" có kết quả đầu là con cú). Rủi ro cao
  nhất ở cảnh không có `keywords` (dùng dòng chữ đầu), vì ảnh được chọn ngẫu nhiên và không lọc
  theo nội dung. Kể cả với tên món cụ thể, các kết quả sau kết quả đầu vẫn có thể lạc: với "cá kho
  tộ", kết quả 2-4 là mì ống, con mèo, xe, nên chọn ngẫu nhiên trong 3 kết quả đầu sẽ ra ảnh lạc
  khoảng 2/3 số lần cho từ khóa này. Đây là đánh đổi giữa đổi ảnh mỗi lần render và độ đúng chủ
  đề. **Mitigation:** người dùng chấp nhận ở bản này; viết `keywords` cụ thể (tên món)
  cho cảnh dễ lạc; xem video trước khi đăng; spec "AI chọn ảnh" sau này sẽ dịch sang từ khóa tiếng
  Anh chuyên ngành và cho AI lọc ảnh theo nội dung.
- **Ảnh Pixabay nhỏ:** API miễn phí chỉ cho cạnh dài tối đa 1280px. Ảnh dọc rộng khoảng 720-850px
  và hơi mờ trên khung 1080px. Ảnh ngang (thường gặp, vì không còn ưu tiên ảnh dọc) chỉ cao
  khoảng 850px; sau khi cắt phần giữa cho khung dọc, chỉ còn vùng khoảng 480×850px của ảnh gốc
  được phóng lên 1080×1920, nên mờ rõ hơn và mất hai bên ảnh. **Mitigation:** người dùng chấp nhận. Muốn ảnh nét hơn thì làm kho
  ảnh riêng (spec sau) hoặc xin Pixabay cấp quyền tải ảnh lớn.
- **Giới hạn lượt gọi** (Pixabay 100 lượt mỗi 60 giây). **Mitigation:**
  cache kết quả 24 giờ, thử lại 1 lần, và dừng với thông báo rõ ràng.
- **Máy chủ ảnh chặn User-Agent mặc định của urllib.** **Mitigation:** gửi User-Agent riêng, và
  kiểm chứng bằng smoke test thật.
- **Lộ key Pixabay** vì key nằm trong URL. **Mitigation:** lọc key khỏi mọi thông báo, có test cho
  việc này.
- **Đường dẫn kéo thả có nhiều dạng khác nhau trên Windows.** **Mitigation:** chuẩn hóa dấu nháy
  và tiền tố `& `, có test cho từng dạng.

## Accepted Decisions

- Tìm bằng tiếng Việt (`lang=vi`) với từ khóa người dùng viết hoặc dòng chữ đầu của cảnh. Thử
  thật trên Pixabay: tên món cụ thể cho kết quả đầu đúng món ("cá kho tộ", "sữa chua", "vừng
  đen"; riêng "cá kho tộ" các kết quả 2-4 đã lạc sang mì ống, xe, con mèo), còn
  cụm từ chung chung hoặc từ nhiều nghĩa dễ lạc ("thực phẩm tốt cho xương" ra cây xương rồng,
  "đậu phụ" có kết quả đầu là con cú). Người dùng chấp nhận, và viết `keywords` cụ thể khi cần.
- Cảnh tiêu đề chỉ tìm khi có `keywords`, vì dòng đầu của tiêu đề không phải tên món.
- Phương án "AI hiểu món ăn": Claude chuyển từ khóa tiếng Việt thành từ khóa tiếng Anh chuyên
  ngành, tìm thêm nguồn Openverse (ảnh CC0/public domain), và Claude xem ảnh để chọn ảnh đúng món,
  ngon mắt, có chỗ cho hộp chữ. Phương án này được tách thành spec sau ("AI chọn ảnh") cắm vào
  bước tìm ảnh của spec này, để có bản dùng được sớm. Spec đó cần `ANTHROPIC_API_KEY` và có chi
  phí mỗi video.
- Câu "image prompt doubles as the stock-search keywords" trong content.md được thay bằng trường
  `keywords` riêng.
- Việc tìm ảnh nằm trong lệnh render, không phải một lệnh `fetch-images` riêng.
- Tool tự chọn ảnh, không tải nhiều ứng viên để người dùng chọn.
- Ảnh tự động đổi mỗi lần render để video đa dạng, và không ghi vào JSON. Lựa chọn là ngẫu nhiên
  và không nhớ lần trước, nên đôi khi một cảnh có thể ra lại ảnh cũ. Phương án lưu lịch sử ảnh
  đã dùng bị loại vì phức tạp.
- Chỉ dùng Pixabay. Nguồn cố định, không cấu hình được, khác với quy ước "provider choice is
  configuration" trong patterns.md. Pexels bị loại vì hai lý do: bản ảnh lớn của Pexels (`large2x`)
  chỉ cao tối đa 1300px nên ảnh dọc gần như không nét hơn Pixabay, và điều khoản API của Pexels bắt
  buộc hiển thị link "Photos provided by Pexels", trái với quyết định không ghi nguồn.
- Không dùng Google Images (bản quyền, không có cách tải tự động hợp lệ). Unsplash bị loại vì bắt
  buộc ghi tác giả. Kho ảnh riêng của người dùng để spec sau.
- Không lưu thông tin nguồn ảnh (tác giả, link, giấy phép), theo ý người dùng. Điều này khác với
  quy định "Store source and license info on the asset" trong architecture.md. Đây là giới hạn đã
  chấp nhận. Giấy phép nội dung Pixabay không bắt buộc ghi nguồn trên video. Riêng điều khoản API
  của Pixabay yêu cầu cho người dùng biết ảnh từ đâu mỗi khi hiển thị kết quả tìm kiếm. CLI không
  hiển thị kết quả tìm kiếm nên chưa áp dụng, nhưng giao diện web sau này nếu hiện danh sách ảnh
  Pixabay thì phải ghi "Ảnh từ Pixabay".
- Ảnh người dùng luôn được ưu tiên. File ảnh không tồn tại thì tìm ảnh thay thế và in cảnh báo,
  không báo lỗi.
- Không tìm được ảnh thì hỏi ngay trong terminal để người dùng bổ sung, rồi render tiếp. Ảnh nhập
  được giữ cố định trong JSON.
- Khi lỗi mạng hoặc bị giới hạn lượt gọi thì dừng chứ không hỏi người dùng, vì ảnh người dùng đưa
  vào sẽ bị ghi cố định vào JSON trong khi kho ảnh thực ra vẫn có ảnh. Người dùng tự bổ sung ảnh
  vào JSON nếu muốn.
- Ảnh ngang và ảnh nhỏ vẫn được chấp nhận. Thà có ảnh hơi mờ hoặc phải cắt còn hơn dừng lại hỏi.
- Khi không đủ ảnh khác nhau thì dùng lại ảnh trùng, không hỏi người dùng.
- Mỗi từ khóa chỉ gọi Pixabay một lần, không lọc hướng ảnh, để tiết kiệm lượt gọi.
- Không ưu tiên ảnh dọc (thay cho quyết định cũ ở câu 14 và 23): thử thật với "cá kho tộ", ảnh dọc
  duy nhất trong 10 kết quả đầu là ảnh con mèo, còn ảnh món đúng là ảnh ngang, nên ưu tiên ảnh dọc
  sẽ luôn chọn ảnh lạc. Chọn ngẫu nhiên trong 3 kết quả liên quan nhất còn lại để vừa sát chủ đề
  vừa có đổi ảnh giữa các lần render.
- Kết quả tìm kiếm được lưu 24 giờ để tuân thủ quy định của Pixabay. Tool vẫn chọn ngẫu nhiên
  (theo quy tắc 3 ứng viên đầu) từ danh sách đã lưu nên ảnh vẫn thay đổi giữa các lần render.
- JSON được định dạng lại khi ghi (thụt lề đều). Nội dung và tiếng Việt giữ nguyên.
- Ngân sách 2× thời lượng video chỉ tính phần render, vì thời gian tìm ảnh phụ thuộc vào mạng.
- Key Pixabay của người dùng đã được lưu vào `.env` trên máy dev và đã gọi thử thành công.

## Testing

**Unit tests:** cần thiết, vì phần thứ tự từ khóa, chọn ảnh, cache và phân loại lỗi là logic thuần,
nhiều nhánh và dễ sai. Chạy bằng pytest, HTTP được giả lập, không gọi mạng thật. Random và hàm
`sleep` được tiêm vào để kết quả xác định và test chạy nhanh. Các phần cần cover:
- Parse `keywords`: hợp lệ; sai kiểu; chuỗi rỗng; dài quá 100 ký tự (lỗi nêu đúng cảnh). Từ khóa
  mặc định của cảnh nội dung là dòng đầu (bỏ `*`, giữ dấu, tối đa 100 ký tự); cảnh tiêu đề không
  có `keywords` thì không tìm. `image`
  trống, vắng mặt hoặc trỏ tới file không tồn tại (có cảnh báo).
- Đọc `.env`: BOM, dấu nháy, `#`, `export`; biến môi trường thật được ưu tiên.
- Thứ tự từ khóa: thử lần lượt, mỗi từ khóa một lần gọi. Cảnh có ảnh hợp lệ không gửi yêu cầu
  nào. Kịch bản đủ ảnh chạy được khi không có key.
- Gửi đúng tham số: Pixabay `lang=vi`, `image_type=photo`, `safesearch=true`, tải `largeImageURL`; mọi yêu cầu có User-Agent
  riêng.
- Chọn ảnh:
  - chỉ chọn ngẫu nhiên trong 3 ứng viên đầu chưa dùng, theo thứ tự Pixabay; ảnh ngang ở vị trí
    đầu được chọn được dù có ảnh dọc ở vị trí sau;
  - ứng viên hỏng hoặc đã dùng bị bỏ, kết quả thứ 4, 5… được lên thay; chỉ xét 10 kết quả đầu;
  - không trùng ảnh trong một video; hết ảnh mới thì sang từ khóa tiếp, hết từ khóa thì dùng lại
    ảnh trùng.
- Cache 24 giờ: lần thứ hai không gọi API; quá hạn thì gọi lại; file cache hỏng thì gọi API lại;
  thư mục cache không ghi được thì render vẫn chạy.
- Ứng viên quá 15 MB, không phải ảnh hoặc ảnh hỏng thì sang ứng viên khác. Hết ứng viên thì sang
  từ khóa tiếp. Hết từ khóa thì ra lỗi có kiểu liệt kê cảnh (khi không có ai để hỏi).
- Lỗi:
  - không có key; không có mạng (lỗi kết nối: đợi, thử lại đúng 1 lần, vẫn lỗi thì dừng; thử lại
    thành công thì tiếp tục và không tính là lỗi mạng);
  - Pixabay 429/5xx/timeout: thử lại đúng 1 lần, vẫn lỗi thì dừng với lỗi có kiểu, không hỏi;
  - Pixabay lỗi key (HTTP 400, nội dung chứa `API key`) thì dừng ngay; 400 khác thì bỏ từ khóa
    kèm cảnh báo, không báo "key không hợp lệ";
  - tải ảnh lỗi mạng: thử ứng viên khác; lần lỗi mạng thứ 2 của cảnh thì dừng; tải quá 15 giây
    (kể cả nhận dữ liệu nhỏ giọt) tính là lỗi mạng;
  - cảnh vừa có từ khóa không kết quả vừa có lỗi mạng thì dừng, không hỏi;
  - mọi thông báo đều không chứa key;
  - FFmpeg không chạy khi tìm ảnh thất bại.
- Ảnh tự động không được ghi vào JSON, và thư mục tạm không còn ảnh sau khi render.
- `image` trỏ tới file không tồn tại: có cảnh báo và cảnh đó được tìm ảnh thay thế.
- Biến môi trường rỗng ghi đè key trong `.env`.
- Cập nhật các test cũ đang coi thiếu ảnh là lỗi (`test_script.py`, `test_cli.py`).

**Integration tests:** cần thiết, vì luồng hỏi người dùng nối tìm ảnh, ghi JSON và render qua
nhiều module, và thứ tự giữa tìm, hỏi và dừng chỉ kiểm chứng được ở ranh giới CLI.
- **CLI và lời hỏi:** gọi `main()` trong cùng tiến trình, HTTP giả lập, stdin giả lập và được
  đánh dấu là terminal (patch `isatty`).
  - Cảnh tiêu đề không có `keywords` và không có ảnh được hỏi ngay khi không có key (khi không
    còn cảnh nào khác cần tìm).
  - Kịch bản trộn mà không có key hoặc mất mạng: dừng trước mọi lời hỏi, JSON không đổi.
  - stdin không phải terminal: lỗi có kiểu, không hỏi.
  - Đường dẫn kéo thả có `"..."`, `'...'` hoặc `& '...'`.
  - Nhập sai rồi nhập đúng; dòng trống; EOF; Ctrl+C.
  - Ảnh được chép đúng tên, có `-2` khi trùng tên, không ghi đè. JSON được ghi đúng, giữ tiếng
    Việt.
  - Ctrl+C giữ lại ảnh đã nhập trước đó và không render.
  - Render chạy tiếp sau khi nhập đủ ảnh.
  - Không có terminal thì ra lỗi có kiểu.
  - CLI in riêng "Tìm ảnh" và "Render".
- **Smoke test thật** (skip kèm lý do nếu không có `PIXABAY_API_KEY` hoặc không có mạng): một lần
  tìm và tải thật từ Pixabay, ảnh tải về mở được bằng Pillow.
- **Render smoke** (cần FFmpeg): kịch bản không có ảnh, HTTP giả lập trả ảnh do Pillow sinh, ra
  MP4 hợp lệ.

**E2E tests:** không cần. Chưa có UI, và CLI đã được test trong tiến trình.

## Verification

### Agent Verification

| Step | Expected Result |
|------|-----------------|
| 1. Chạy `pytest` trong `worker/` với FFmpeg và key Pixabay | Toàn bộ test pass. Smoke test thật không bị skip |
| 2. Xóa thư mục `reels_render_cache` trong thư mục tạm của máy, tạo bản sao `samples/xuong-khop.json` trong `out/` với `image` của mọi cảnh để trống, rồi render bằng CLI | Mã thoát 0. In đường dẫn và dòng "Tìm ảnh: …s (N lượt gọi API) · Render: …s" với N > 0. Video 1080×1920 có ảnh ở mọi cảnh. JSON bản sao không đổi |
| 3. Render lại bản sao đó lần nữa trong vòng 24 giờ | Số lượt gọi API nhỏ hơn bước 2 (thường là 0, vì các từ khóa đã có trong cache). Trích khung giữa mỗi cảnh của hai video và ghi lại cảnh nào đổi ảnh (thông tin để người dùng xem, không phải điều kiện đạt vì lựa chọn là ngẫu nhiên) |
| 4. Render `samples/xuong-khop.json` (đủ ảnh) với biến môi trường `PIXABAY_API_KEY=` (rỗng) | Render thành công, dòng in ra có "0 lượt gọi API" |
| 5. Trích một khung giữa mỗi cảnh của video ở bước 2 ra `out/frames-stock/` | Có file PNG để người dùng xem |

### User Verification
- Xem video ở bước 2 và các khung trong `out/frames-stock/`: ảnh có đúng món ăn và đủ đẹp để đăng
  không. Phần này cần người xem vì agent không đánh giá được ảnh có hợp chủ đề hay không.
- Thử luồng hỏi ảnh trên terminal thật: viết một cảnh có `keywords` vô nghĩa (ví dụ `["xyzqwv"]`), kéo thả một ảnh từ
  máy vào khi được hỏi, rồi kiểm tra ảnh được chép vào thư mục kịch bản và video render tiếp.
  Phần này cần người dùng vì thao tác kéo thả không giả lập được hoàn toàn.
