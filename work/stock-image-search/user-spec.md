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
trong kịch bản JSON (cả cảnh tiêu đề) có thêm trường `keywords`: danh sách từ khóa tiếng Anh, sắp
từ cụ thể đến chung. Khi render, cảnh nào chưa có ảnh của người dùng sẽ được tự tìm ảnh chụp thật
trên Pixabay, rồi tải về và dùng cho lần render đó.

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
                 "keywords": ["healthy food for strong bones", "calcium rich food"] },
     "scenes": [
       { "text": "Cá nhỏ ăn cả xương\nGiàu *canxi*", "seconds": 4,
         "keywords": ["small fried fish", "fried fish", "fish dish"] },
       { "text": "Sữa chua\nBổ sung *canxi*", "seconds": 4, "image": "xuong-khop/02-sua-chua.jpg" }
     ]
   }
   ```

2. Người dùng chạy lệnh render như cũ:
   `python -m reels_render script.json -o out/video.mp4`.
3. Với từng cảnh, tool quyết định nguồn ảnh như sau:
   - Có `image` trỏ tới file tồn tại: luôn dùng ảnh đó, không tìm.
   - `image` trống hoặc không có: tìm theo `keywords`.
   - `image` trỏ tới file không tồn tại: in cảnh báo (ví dụ
     `Cảnh 2: không thấy file anh-ca.jpg, sẽ tìm ảnh thay thế`) rồi tìm theo `keywords`.
4. Tool tìm cho mọi cảnh cần tìm. Tool thử từng từ khóa theo thứ tự trên Pixabay, và chỉ sang
   từ khóa tiếp theo khi từ khóa hiện tại không cho ảnh dùng được. Trong 10 kết quả đầu, tool chọn ngẫu nhiên một ảnh dọc chưa dùng cho cảnh khác trong cùng video. Chỉ
   khi không còn ảnh dọc nào thì mới chọn ngẫu nhiên trong các ảnh ngang. Ảnh được tải về thư mục
   tạm.
5. Cảnh không có ảnh dùng được sau khi thử hết từ khóa (hoặc không có `keywords`):
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
      không rỗng (sau khi bỏ khoảng trắng hai đầu) và tối đa 100 ký tự. Tool không kiểm tra ngôn
      ngữ, nhưng người viết nên dùng tiếng Anh vì Pixabay tìm tiếng Việt cho kết quả kém.
      `keywords: []` được coi như không có `keywords`.
- [ ] `keywords` sai kiểu (không phải danh sách, phần tử không phải chuỗi, chuỗi rỗng, dài quá 100
      ký tự) báo lỗi tiếng Việt nêu đúng cảnh ngay khi đọc kịch bản, trước khi tìm ảnh.
- [ ] `image` trở thành tùy chọn. `image` rỗng hoặc vắng mặt không còn là lỗi.
- [ ] `samples/xuong-khop.json` được bổ sung `keywords` cho cả 6 cảnh. Các ảnh mẫu hiện có vẫn
      được dùng.

**Chọn và tìm ảnh**
- [ ] Cảnh có `image` trỏ tới file tồn tại luôn dùng ảnh đó và không gửi yêu cầu tìm kiếm nào.
- [ ] Cảnh có `image` trỏ tới file không tồn tại thì in cảnh báo nêu cảnh và tên file, rồi tìm ảnh
      thay thế theo `keywords`.
- [ ] Từ khóa được thử theo đúng thứ tự trong danh sách, mỗi từ khóa gọi Pixabay đúng một lần.
      Pixabay là nguồn ảnh duy nhất.
- [ ] Chỉ lấy ảnh chụp (Pixabay `image_type=photo`). Ứng viên là 10 kết quả đầu của mỗi lần
      tìm. Tool chọn ngẫu nhiên trong các ảnh dọc (cao > rộng) chưa dùng. Chỉ khi không còn ảnh
      dọc nào mới chọn ngẫu nhiên trong ảnh ngang hoặc vuông chưa dùng (lõi render cắt phần giữa
      như hiện nay). Không loại ảnh vì kích thước nhỏ.
- [ ] Ảnh tải bản `largeImageURL` của Pixabay.
- [ ] Không lưu lịch sử lựa chọn giữa các lần render.
- [ ] Hai cảnh trong cùng video không dùng chung một ảnh tự động. Nếu không còn ảnh mới, cảnh sau
      thử từ khóa tiếp theo. Thử hết vẫn không có ảnh mới thì dùng lại ảnh trùng, không hỏi
      người dùng.
- [ ] Ảnh tự động được tải vào thư mục tạm của lần render và xóa sau khi render. Không ghi ảnh
      tự động vào JSON hay vào repo.
- [ ] Kết quả tìm kiếm (danh sách ảnh của mỗi từ khóa) được lưu 24 giờ trong thư mục tạm
      của máy. Trong 24 giờ đó, cùng từ khóa không gọi lại API mà chọn ngẫu nhiên từ danh sách đã
      lưu. Quá 24 giờ thì gọi lại.
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
- [ ] `PIXABAY_API_KEY` trống hoặc vắng mà có cảnh cần tìm: dừng ngay với lỗi có kiểu, hướng dẫn đặt key vào `.env`, không hỏi người dùng.
- [ ] Không có mạng khi cần tìm: dừng với lỗi có kiểu, không hỏi người dùng.
- [ ] Việc kiểm tra key và mạng chỉ áp dụng khi có ít nhất một cảnh thiếu ảnh và có `keywords`.
      Tìm ảnh luôn chạy xong trước mọi lời hỏi, nên kịch bản trộn mà thiếu key hoặc mất mạng sẽ
      dừng trước khi hỏi và JSON không bị sửa.
- [ ] Pixabay trả 429, lỗi 5xx hoặc hết thời gian chờ (15 giây mỗi yêu cầu): đợi 5 giây, thử lại
      1 lần. Vẫn lỗi thì dừng với lỗi có kiểu (ví dụ "Pixabay đang giới hạn lượt tìm, thử lại sau
      1 phút"), không hỏi người dùng.
- [ ] Pixabay báo key sai hoặc bị thu hồi: dừng ngay với thông báo "Key Pixabay không hợp lệ, kiểm
      tra file .env". Dấu hiệu nhận biết (đã gọi thử ngày 2026-10-29): HTTP 400 với nội dung chứa
      `API key`, ví dụ `[ERROR 400] Invalid API key...` hoặc
      `[ERROR 400] Invalid or missing API key...`. Phản hồi 400 khác (ví dụ
      `[ERROR 400] "per_page" is out of valid range.`) không được báo là lỗi key.
- [ ] Pixabay từ chối một từ khóa vì lý do khác (lỗi 4xx khác 429, không phải lỗi key): bỏ qua từ
      khóa đó, in cảnh báo, tiếp tục.
- [ ] Tải ảnh lỗi mạng (403, timeout, mất kết nối): thử ứng viên khác. Nếu mọi thất bại của một
      cảnh đều là lỗi mạng thì dừng với lỗi có kiểu, không hỏi.
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
- [ ] CLI in riêng thời gian tìm ảnh (kèm số lượt gọi API tìm kiếm) và thời gian render. Ngân
      sách render (≤ 2× thời lượng video) chỉ áp dụng cho phần render.

**Tài liệu dự án**
- [ ] Project Knowledge được cập nhật cho khớp hành vi mới:
  - `architecture.md`: thiếu ảnh không còn là lỗi; có `keywords`; không lưu nguồn ảnh; Pixabay là
    nguồn ảnh stock duy nhất (bỏ Pexels khỏi bảng tích hợp).
  - `content.md`: từ khóa tìm ảnh là trường `keywords` riêng.
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
- **Ảnh Pixabay nhỏ:** API miễn phí chỉ cho cạnh dài tối đa 1280px, nên ảnh dọc rộng khoảng 720px
  và hơi mờ trên khung 1080px. **Mitigation:** người dùng chấp nhận. Muốn ảnh nét hơn thì làm kho
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

- Từ khóa là trường `keywords` tiếng Anh do người dùng viết, thay vì gọi Claude để dịch chữ trên
  cảnh. Pixabay tìm bằng tiếng Việt cho kết quả rất kém. Sau này spec viết kịch bản bằng
  Claude sẽ tự điền trường này. Như vậy câu "image prompt doubles as the stock-search keywords"
  trong content.md được thay bằng trường `keywords` riêng.
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
  quy định "Store source and license info on the asset" trong architecture.md. Giấy phép Pixabay
  không bắt buộc ghi nguồn. Đây là giới hạn đã chấp nhận.
- Ảnh người dùng luôn được ưu tiên. File ảnh không tồn tại thì tìm ảnh thay thế và in cảnh báo,
  không báo lỗi.
- Không tìm được ảnh thì hỏi ngay trong terminal để người dùng bổ sung, rồi render tiếp. Ảnh nhập
  được giữ cố định trong JSON.
- Khi lỗi mạng hoặc bị giới hạn lượt gọi thì dừng chứ không hỏi người dùng, vì ảnh người dùng đưa
  vào sẽ bị ghi cố định vào JSON trong khi kho ảnh thực ra vẫn có ảnh. Người dùng tự bổ sung ảnh
  vào JSON nếu muốn.
- Ảnh ngang và ảnh nhỏ vẫn được chấp nhận. Thà có ảnh hơi mờ hoặc phải cắt còn hơn dừng lại hỏi.
- Khi không đủ ảnh khác nhau thì dùng lại ảnh trùng, không hỏi người dùng.
- Mỗi từ khóa chỉ gọi Pixabay một lần, không lọc hướng ảnh, để tiết kiệm lượt gọi. Ảnh dọc được
  xếp lên trước ở phía tool.
- Kết quả tìm kiếm được lưu 24 giờ để tuân thủ quy định của Pixabay. Tool vẫn chọn ngẫu nhiên từ
  danh sách đã lưu nên ảnh vẫn đa dạng.
- JSON được định dạng lại khi ghi (thụt lề đều). Nội dung và tiếng Việt giữ nguyên.
- Ngân sách 2× thời lượng video chỉ tính phần render, vì thời gian tìm ảnh phụ thuộc vào mạng.
- Key Pixabay của người dùng đã được lưu vào `.env` trên máy dev và đã gọi thử thành công.

## Testing

**Unit tests:** cần thiết, vì phần thứ tự từ khóa, chọn ảnh, cache và phân loại lỗi là logic thuần,
nhiều nhánh và dễ sai. Chạy bằng pytest, HTTP được giả lập, không gọi mạng thật. Random và hàm
`sleep` được tiêm vào để kết quả xác định và test chạy nhanh. Các phần cần cover:
- Parse `keywords`: hợp lệ; sai kiểu; chuỗi rỗng; dài quá 100 ký tự (lỗi nêu đúng cảnh). `image`
  trống, vắng mặt hoặc trỏ tới file không tồn tại (có cảnh báo).
- Đọc `.env`: BOM, dấu nháy, `#`, `export`; biến môi trường thật được ưu tiên.
- Thứ tự từ khóa: thử lần lượt, mỗi từ khóa một lần gọi. Cảnh có ảnh hợp lệ không gửi yêu cầu
  nào. Kịch bản đủ ảnh chạy được khi không có key.
- Gửi đúng tham số: Pixabay `image_type=photo`, tải `largeImageURL`; mọi yêu cầu có User-Agent
  riêng.
- Chọn ảnh:
  - có ảnh dọc chưa dùng thì chỉ chọn trong ảnh dọc; không còn ảnh dọc mới dùng ảnh ngang;
  - chỉ chọn trong 10 kết quả đầu;
  - không trùng ảnh trong một video; hết ảnh mới thì sang từ khóa tiếp, hết từ khóa thì dùng lại
    ảnh trùng.
- Cache 24 giờ: lần thứ hai không gọi API; quá hạn thì gọi lại; file cache hỏng thì gọi API lại;
  thư mục cache không ghi được thì render vẫn chạy.
- Ứng viên quá 15 MB, không phải ảnh hoặc ảnh hỏng thì sang ứng viên khác. Hết ứng viên thì sang
  từ khóa tiếp. Hết từ khóa thì ra lỗi có kiểu liệt kê cảnh (khi không có ai để hỏi).
- Lỗi:
  - không có key; không có mạng;
  - Pixabay 429/5xx/timeout: thử lại đúng 1 lần, vẫn lỗi thì dừng với lỗi có kiểu, không hỏi;
  - Pixabay lỗi key (HTTP 400, nội dung chứa `API key`) thì dừng ngay; 400 khác thì bỏ từ khóa
    kèm cảnh báo, không báo "key không hợp lệ";
  - tải ảnh lỗi mạng ở mọi ứng viên thì dừng;
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
  - Cảnh không có `keywords` và không có ảnh được hỏi ngay khi không có key.
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
| 2. Tạo bản sao `samples/xuong-khop.json` trong `out/` với `image` của mọi cảnh để trống, rồi render bằng CLI | Mã thoát 0. In đường dẫn và dòng "Tìm ảnh: …s (N lượt gọi API) · Render: …s" với N > 0. Video 1080×1920 có ảnh ở mọi cảnh. JSON bản sao không đổi |
| 3. Render lại bản sao đó lần nữa trong vòng 24 giờ | Dòng in ra có "0 lượt gọi API" (dùng cache). Trích khung giữa mỗi cảnh của hai video và ghi lại cảnh nào đổi ảnh (thông tin để người dùng xem, không phải điều kiện đạt vì lựa chọn là ngẫu nhiên) |
| 4. Render `samples/xuong-khop.json` (đủ ảnh) với biến môi trường `PIXABAY_API_KEY=` (rỗng) | Render thành công, dòng in ra có "0 lượt gọi API" |
| 5. Trích một khung giữa mỗi cảnh của video ở bước 2 ra `out/frames-stock/` | Có file PNG để người dùng xem |

### User Verification
- Xem video ở bước 2 và các khung trong `out/frames-stock/`: ảnh có đúng món ăn và đủ đẹp để đăng
  không. Phần này cần người xem vì agent không đánh giá được ảnh có hợp chủ đề hay không.
- Thử luồng hỏi ảnh trên terminal thật: viết một cảnh có `keywords` vô nghĩa, kéo thả một ảnh từ
  máy vào khi được hỏi, rồi kiểm tra ảnh được chép vào thư mục kịch bản và video render tiếp.
  Phần này cần người dùng vì thao tác kéo thả không giả lập được hoàn toàn.
