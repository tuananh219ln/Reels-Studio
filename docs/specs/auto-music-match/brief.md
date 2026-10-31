# Brief: Tự động gắn nhạc từ thư viện theo chủ đề của video

> Brief bàn giao cho coding agent. Trước khi làm, đọc `AGENTS.md`, `docs/decisions.md`,
> `docs/architecture.md` (mục Web App — Music Library) và `docs/content.md` (mục Music).
> Người duyệt cuối: owner. Báo cáo trong PR theo mẫu 3 phần của `AGENTS.md`.
> Ngày lập brief: 2026-10-31.

## Vấn đề

Kịch bản sinh xong, video vẫn chưa có nhạc: thành viên phải tự vào thẻ nhạc, tự nhớ
thư viện có bài gì, tự chọn. Trong khi đó thư viện nhạc của team đã được gắn nhãn sẵn
theo chủ đề và tâm trạng, và kịch bản cũng đã biết chủ đề của video — hai đầu này chưa
được nối với nhau. Gợi ý nhạc hiện tại (`music_suggestions`) chỉ là tên bài để tìm
trong thư viện TikTok/Facebook lúc đăng bài, không liên quan tới thư viện của team.

## Sự thật trong code hiện tại (đã rà soát 2026-10-31)

- Thư viện nhạc: `api/src/reels_api/routes_music.py` — danh sách cố định
  `TOPICS = ["tuổi thọ", "tim mạch", "máu não", "xương khớp", "gan", "da tóc",
  "giấc ngủ", "giảm cân", "chung"]` và
  `MOODS = ["nhẹ nhàng", "piano", "thư giãn", "truyền cảm hứng", "vui tươi",
  "trầm lắng"]`. Mỗi track có `topics` (nhiều) + `mood` (một). `GET /music` đã lọc
  được theo `?topic=` và `?mood=`.
- Gắn nhạc từ thư viện vào video đã có sẵn: `POST /videos/{id}/music/from-library`
  trong `routes_videos.py` — chép file của track vào thư mục của video và trả tên
  file theo quy ước đặt tên của thư viện. Nhạc đã gắn là bản chép: xoá track khỏi
  thư viện không ảnh hưởng video.
- Job script: `run_script_job` trong `jobs.py` dựng prompt bằng `build_script_prompt`
  rồi `save_script` lưu kết quả, trong đó có `music_suggestions`. Định dạng đầu ra là
  CODE cố định (`OUTPUT_FORMAT` trong `claude.py`, xem quyết định "prompt là dữ
  liệu, format là code" trong `docs/decisions.md`).
- Chưa có trường nào trên video ghi lại "chủ đề nhạc" hay "mood nhạc" — muốn gắn
  lại nhạc mà không gọi lại Claude thì cần lưu hai giá trị này.

## Thiết kế đề xuất

### 1. Claude chọn nhãn nhạc trong cùng một lượt gọi kịch bản

- Thêm vào `OUTPUT_FORMAT` trong `claude.py` hai trường bắt buộc:
  `music_topic` (đúng MỘT giá trị trong `TOPICS`) và `music_mood` (đúng MỘT giá trị
  trong `MOODS`). Danh sách cho phép trong prompt phải lấy từ chính hai hằng số ở
  `routes_music.py` (import dùng chung, không gõ lại danh sách ở nơi khác).
- `parse_output` kiểm tra hai trường này thuộc danh sách cho phép; sai/thiếu thì coi
  như đầu ra không dùng được theo cơ chế thử lại hiện có của `call_claude` (không
  thêm cơ chế retry mới).
- Migration thêm 2 cột vào bảng `videos`: `music_topic`, `music_mood` (nullable).
  `save_script` lưu hai giá trị này mỗi khi sinh/nhân bản kịch bản.

### 2. Thuật toán khớp nhạc (một hàm dùng chung)

- Hàm mới đặt cạnh logic thư viện (module dùng chung cho cả job lẫn endpoint, không
  viết hai bản): nhận `music_topic` + `music_mood`, trả về track phù hợp nhất hoặc
  `None`. Thứ tự ưu tiên:
  1. Track có `music_topic` trong `topics` VÀ `mood` == `music_mood`.
  2. Track có `music_topic` trong `topics` (bất kỳ mood).
  3. Track có `"chung"` trong `topics` VÀ `mood` == `music_mood`.
  4. Track có `"chung"` trong `topics`.
  Cùng hạng thì lấy track mới thêm gần nhất. Ngoài 4 hạng trên: không gắn (trả `None`).
- Việc chép file vào video dùng lại đúng logic của endpoint `from-library` hiện có
  (trích ra hàm dùng chung nếu cần) — không chép file theo cách thứ hai.

### 3. Tự gắn sau khi sinh kịch bản + gắn lại bằng tay

- Cuối `run_script_job` (cả `script` lẫn `clone`), sau `save_script`: nếu video CHƯA
  có nhạc thì chạy thuật toán khớp; khớp được thì gắn luôn và ghi log của job (tên
  track đã chọn). Video đã có nhạc (upload tay hoặc chọn từ thư viện) thì TUYỆT ĐỐI
  không đụng vào.
- Endpoint mới `POST /videos/{id}/music/auto` cho video đã có sẵn kịch bản: dùng
  `music_topic`/`music_mood` đã lưu của video để gắn lại (đổi sang track khác phù
  hợp nhất khác track hiện tại nếu có). Video cũ chưa có hai trường này (kịch bản
  sinh trước tính năng này) → trả lỗi rõ ràng, và thẻ nhạc cho thành viên tự chọn
  nhãn topic/mood rồi mới bấm gắn (hai trường được lưu lại từ lần chọn đó).
- Web UI: thẻ nhạc hiển thị trạng thái tự gắn — "Đã tự gắn: <tên track> (chủ đề:
  <music_topic>, mood: <music_mood>)" kèm nút "Đổi bài khác" gọi endpoint `auto`.
  Không khớp được bài nào → thẻ nhạc hiện gợi ý cụ thể thư viện đang thiếu gì, ví
  dụ: "Thư viện chưa có bài nào gắn nhãn 'xương khớp' hoặc 'chung'".

## Không làm

- Không thay đổi `music_suggestions` hiện tại (vẫn phục vụ việc đăng TikTok/Facebook).
- Không tải nhạc từ TikTok/Facebook hay nguồn ngoài vào thư viện.
- Không tự gắn nhạc ở thời điểm render; không gắn khi video đã có nhạc.
- Không thêm nhãn topic/mood mới ngoài hai danh sách cố định hiện có.

## Tiêu chí nghiệm thu

1. Sinh kịch bản cho video chủ đề xương khớp (thư viện local có ít nhất 1 track gắn
   nhãn `xương khớp` và 1 track `chung`): video tự có nhạc ngay khi job xong, đúng
   track ưu tiên theo thuật toán, tên track xuất hiện trong log job.
2. Video đã có nhạc do thành viên upload → chạy lại job script → nhạc giữ nguyên.
3. Thư viện không có track nào khớp cả 4 hạng → video không có nhạc, thẻ nhạc hiện
   gợi ý thiếu nhãn gì, job script vẫn `done` (thiếu nhạc không làm hỏng job).
4. Claude trả `music_topic` ngoài danh sách → đầu ra bị coi là không dùng được và
   đi theo đường thử-lại-rồi-báo-lỗi hiện có, thông điệp như các lỗi format khác.
5. Bấm "Đổi bài khác" trên video đã tự gắn → nhạc đổi sang track phù hợp kế tiếp
   (nếu còn), render sau đó dùng bài mới.
6. Video cũ (chưa có `music_topic`): chọn nhãn tay trong thẻ nhạc → gắn được và hai
   trường được lưu.
7. Test xanh: `ruff`, `pytest` (api — có test đơn vị cho thứ tự ưu tiên của thuật
   toán khớp và test job script với fake Claude trả nhãn nhạc), test worker, `lint`
   + `typecheck` + `test:e2e` (web). Không gọi API thật trong test.

## Trường hợp biên phải xử lý

- Track được chọn bị xoá khỏi thư viện ngay trước khi chép file → coi như không
  khớp, thử hạng ưu tiên tiếp theo; không để job chết.
- Hai video sinh cùng lúc cùng khớp một track → cả hai cùng gắn được (file được chép
  riêng cho từng video, thư viện không bị khoá).
- `music_topic` = `"chung"` → các hạng 1–2 và 3–4 trùng nhau; thuật toán vẫn chạy
  đúng (khớp theo mood trước).
- Migration chạy trên DB production đã có video cũ: hai cột nullable, không backfill.

## Việc ghi chép đi kèm (cùng PR)

- Cập nhật `docs/architecture.md` (hai cột mới, endpoint `auto`, bước tự gắn trong
  job script) và `docs/content.md` nếu cách mô tả thẻ nhạc thay đổi.
- Ghi quyết định mới vào `docs/decisions.md` (có ngày): nhãn nhạc do Claude chọn
  trong cùng lượt gọi kịch bản từ hai danh sách cố định; nhạc tự gắn không bao giờ
  ghi đè lựa chọn của thành viên.
- Mục tính năng này đã có trong `backlog.md` ở thư mục gốc repo (thêm 2026-10-31);
  gỡ mục đó khi xong, theo luật backlog của repo.
