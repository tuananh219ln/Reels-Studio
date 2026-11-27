# Phân tích: vì sao bấm "Duyệt" lại tự hẹn giờ — và sửa tận gốc ra sao

Ngày phân tích: 27/11/2026. Code đối chiếu: nhánh main của tuananh219ln/Reels-Studio @ 472d4b0 (merge PR #374), truy cập ngày 27/11/2026 qua `git fetch origin main` + `git show origin/main:<path>`. Mọi khẳng định về code đều có trích dẫn file/dòng ở mục 2 và Phụ lục A. Các app ngoài được tra cứu trên web ngày 27/11/2026, nguồn ghi ở mục 4 và Phụ lục B.

## 1. Vụ video 78 — tóm tắt

- Video 78: "Sau 60 tuổi đau gối? 5 động tác ngồi ghế làm mỗi sáng", nhóm Già (topic 6), Page Già Mà Khỏe (fanpage 7). Video cũ, KHÔNG gắn plan_idea nên không có giờ đăng gợi ý (`suggested_post_at` = null).
- 27/11 00:07: video còn ở trạng thái Chờ duyệt (`pending_review`), trong danh sách 8 video chờ.
- 27/11 00:08: được duyệt qua Telegram (nút Duyệt trong tin `/cho_duyet`), rồi bấm "Thêm vào hàng chờ" — xem phân tích đường đi ở §2.3 và §3.
- Trong vòng 1 phút sau: worker lấp khung xếp video vào khung trống gần nhất: 28/11 07:00 VN (publication 761, `scheduled_at` 2026-11-28T00:00:00Z), vì 3 khung 27/11 (07:00/11:00/18:00) đã đầy video 437/438/439. Sau đó hàng chờ rỗng.
- 27/11 00:25: user phát hiện video "nhảy" vào lưới Lịch đăng ở ô 28/11 07:00, yêu cầu phân tích lại việc hẹn giờ/lịch đăng cho đồng bộ.
- 27/11 00:28: user chọn phương án tạm thời: hủy hẹn 78, trả khung 28/11 07:00 cho lô dựng 16:00.
- 27/11 00:35: hủy xong qua web ("Hủy đăng", publication 761 → cancelled). Video vẫn ở trạng thái Đã duyệt + "Chờ đăng", KHÔNG nằm trong hàng chờ nên không tự xếp lại; khung 28/11 07:00 đã trống. (Bài học này khớp đúng code ở §2.7.)

Câu hỏi cần trả lời: (1) vì sao "duyệt" lại đồng nghĩa "hẹn giờ"; (2) vì sao giờ gợi ý của plan bị bỏ qua; (3) vì sao một video lẻ có thể chiếm khung của lô dựng ngày mai.

## 2. Cơ chế hiện tại

### 2.1. Lớp "duyệt" ở lõi: chỉ đổi trạng thái, không hẹn giờ

`api/src/reels_api/review.py:137-164` — `review.approve(db, video, user_id, via, acknowledge_qc)`:

- Chỉ cho duyệt khi video đang `pending_review`, đã render xong (có MP4, không có job render đang chạy), không có mục QC blocker; mục warn cần `acknowledge_qc` ("Vẫn duyệt").
- Khi duyệt: chuyển `review_status` → `approved`, ghi `approved_by/at/via` + `approved_signature` (dấu vân tay của MP4 lúc duyệt). Không tạo Publication, không đụng hàng chờ, không hẹn giờ.
- `review.reject` (166–177): không bỏ được video đã hẹn giờ/đã đăng — "Video đã hẹn giờ hoặc đã đăng, hãy hủy bài trước khi bỏ video". Bỏ thì xóa luôn queue item.
- Mọi route hẹn/đăng đều từ chối video chưa duyệt (409 `not_approved`) — `review.ensure_approved` (227), quyết định 2026-11-26-review-gate.
- Kết luận: bản thân "duyệt" trong lõi là sạch. Việc hẹn giờ đi kèm đến từ các lớp gọi nó (web/Telegram/MCP), mỗi nơi một kiểu.

### 2.2. Web: hai nút cùng nhãn "Duyệt" nhưng khác hành vi

Trên trang chi tiết video (tab "Đăng bài", `PublishTab.tsx:64` render `ReviewCard`) có hai nút "Duyệt":

(a) `ReviewCard.tsx:114-117` — nút "✓ Duyệt" (testid `review-approve`):

- Gọi `POST /api/review/{id}/approve` (`routes_review.py:32-40`) → chỉ duyệt, không hẹn giờ. Còn mục warn thì hiện "Vẫn duyệt" (`ReviewCard.tsx:46-58`).
- Đây là nút duyệt "thuần".

(b) `ApproveVideoButton.tsx` — nút "Duyệt" (dùng ở danh sách video `VideoActions.tsx:168`, thẻ trạng thái `StatusCard.tsx:221`, tab kế hoạch `PlanTab.tsx:1538`):

- Bước 1 (`approve()`): đọc `video.plan_idea?.suggested_post_at`. Không có giờ gợi ý → từ chối: "Video chưa có giờ đăng dự kiến trong kế hoạch". Giờ đã qua → từ chối. Kiểm tra MP4 mới nhất, Page của user, QC blocker.
- Bước 2 (`send()`): hiện Popconfirm "Duyệt đăng lúc {giờ}?" với dòng "Video sẽ tự đăng lên Facebook, Page …, vào giờ này."; bấm xác nhận thì gọi duyệt trước (nếu chưa duyệt) rồi `POST /videos/{id}/publish` với `scheduled_at` = giờ gợi ý của plan.
- Tức là nút này = duyệt + hẹn đúng giờ plan, một cú bấm. Thiết kế này có chủ ý từ quyết định 2026-11-12-plan-approve-button ("Duyệt đăng lúc ...?", "Approval stays a manual gate per idea; nothing is scheduled without a member's tap").

(c) Ngoài ra, drawer "Đăng bài" (`PublishCard.tsx:185-191`): chọn "Đăng ngay" hoặc "Hẹn giờ" (ô datetime-local) → `POST /videos/{id}/publish` (`routes_videos.py`, hàm publish): yêu cầu video đã duyệt (`review.ensure_approved`), giờ hẹn phải sau ít nhất 15 phút và trong 29 ngày tới. Đây là đường hẹn giờ tay chính xác duy nhất trên web.

Hệ quả cho vụ 78: video 78 không có plan_idea → nút (b) từ chối ngay từ bước 1. Muốn đăng 78, người dùng chỉ còn hai đường: (a) duyệt thuần rồi mở drawer Đăng bài hẹn tay, hoặc đi qua Telegram/hàng chờ — tức đúng đường "lấy khung trống gần nhất".

### 2.3. Telegram: duyệt và xếp hàng là hai bước, nhưng bước hai giấu giờ đăng

Luồng `/cho_duyet` (`telegram_commands.py:95-124`, `telegram.py:254-388`):

1. `/cho_duyet` → `pending()` liệt kê tối đa 10 video chờ duyệt của user (mới nhất trước), mỗi video một nút `rv:<id>`.
2. Bấm video → `button("rv")` → `send_review()` gửi MP4 kèm nút "✅ Duyệt" (`ap:<id>:<signature>`) và "❌ Bỏ video" (`rj:<id>:<signature>`), thêm link "Mở trong app".
3. Bấm "✅ Duyệt" → `_button()` gọi `review.approve(via="telegram")` — chỉ duyệt. Nếu còn mục warn chưa xác nhận thì bot gửi lại tin cảnh báo + nút "✅ Vẫn duyệt" (`aq:`).
4. Ngay sau khi duyệt xong, `telegram_commands.offer_queue()` (`telegram_commands.py:286-297`) gửi tin mới: "✅ Đã duyệt: \<tên video\>. Thêm vào hàng chờ của Page? Giờ đăng do hàng chờ tự xếp." kèm nút "➕ Hàng chờ {tên Page}" (`qa:<video>:<page>`) cho mỗi Page của user thuộc nhóm của video.
5. Bấm "➕ Hàng chờ …" → `button("qa")` → `routes_queue.add()` → video vào hàng chờ. Worker lấp khung trong vòng 60 giây (xem §2.5).

Hai điểm đáng chú ý:

- Câu "Giờ đăng do hàng chờ tự xếp" có nói là không chọn giờ, nhưng tin nhắn không nói KHUNG NÀO sẽ xếp — người bấm không biết trước video sẽ rơi vào 28/11 07:00 hay 29/11 18:00.
- Chỉ có một lựa chọn duy nhất trong tin này: vào hàng chờ, hoặc không làm gì (muốn hẹn giờ khác phải tự mở app → Đăng bài → Hẹn giờ). Không có nút "Chọn giờ khác" ngay tại chỗ.

Đường đi của 78 khớp đúng luồng này: duyệt qua Telegram 00:08 (publication 761 ghi created_by NamTC), sau đó video vào hàng chờ và được xếp lịch. (Chuỗi bấm chính xác là suy luận từ code + timeline; không có log thao tác để khẳng định tuyệt đối — xem "Chưa xác minh được".)

### 2.4. MCP (Muse): bốn chế độ trong một tool

`approve_video` (`api/src/reels_api/mcp_server.py:615-655`), tham số `publish`:

- `none` (mặc định): chỉ duyệt.
- `queue`: duyệt rồi thêm vào hàng chờ Page (fanpage_id không bắt buộc — không có thì suy ra Page của user thuộc nhóm của video; hai Page cùng nhóm thì lấy Page có hàng chờ ngắn hơn — `routes_queue._page_for`).
- `now`: duyệt và đăng ngay.
- `schedule`: duyệt và hẹn đúng `schedule_at` (bắt buộc kèm `schedule_at` và `fanpage_id`).

Các tool liên quan:

- `schedule_video` (`mcp_server.py:2933-2945`): "Như nút 'Thêm vào hàng chờ': … hàng chờ tự hẹn giờ vào khung giờ đăng trống tiếp theo của Page (trong 48 giờ tới), không chọn giờ ở đây và không đăng ngay."
- `schedule_video_at` (835–855): hẹn giờ chính xác; bỏ trống `post_at` thì dùng giờ gợi ý của plan, không có giờ gợi ý (hoặc đã qua) thì báo lỗi.
- `unschedule_video` (868–880): chỉ xóa queue item; "Bài đã được hẹn giờ thì không còn trong hàng chờ và không bị huỷ ở đây" — video đã lên lịch thì tool này 404.

### 2.5. Hàng chờ + worker: "khung trống gần nhất", không biết plan là gì

`api/src/reels_api/page_queue.py` (docstring đầu file nói rõ triết lý: "rendered videos wait in order, and the worker gives the first one the Page's next free posting time"):

- Hằng số (dòng 33–38): `FILL_AHEAD = 48 giờ`, `FILL_LEAD = 30 phút`, `SLOT_GAP = 30 phút`, `MAX_ITEMS = 100`.
- `fill()` (114–135): mỗi Page tối đa 1 video/lượt; lấy video đầu hàng chờ "đi được" (có MP4 mới nhất, không có lý do chặn ở `problem()` — gồm QC blocker, trùng MP4 đã đăng trên Page, sai brand — và không có job đang chạy).
- `free_slots()` (57–73): các giờ đăng của Page (giờ riêng của Page, nếu không thì giờ của nhóm — `post_times()`, dòng 41–47) trong cửa sổ [now+30', now+48h], trừ các khung đã có bài (Publication Facebook còn mở) trong vòng ±30'. Múi giờ theo Page/nhóm (`timezone_of()`, dòng 49–55; PR #366/#370).
- `_fill_page()` (137–165): tạo Publication với `scheduled_at` = khung trống ĐẦU TIÊN, ghi `slot_local`/`slot_timezone`, tạo Job publish, xóa queue item. Toàn bộ quá trình KHÔNG đọc `suggested_post_at` ở bất cứ chỗ nào.
- Worker gọi `page_queue.fill_due()` mỗi 60 giây giữa các job (`worker.py:185-193`, `POST_CHECK_SECONDS = 60.0` dòng 53). Vì vậy video vào hàng chờ sẽ được xếp lịch trong vòng tối đa ~60 giây, không cần ai bấm thêm.
- `routes_queue.add()` (route "Thêm vào hàng chờ"): video xếp cuối hàng (position tăng dần); một video chỉ ở một hàng chờ; hàng chờ tối đa 100 video. `routes_queue.remove()` ("Bỏ khỏi hàng chờ"): xóa item; bài đã hẹn thì không bị hủy ("A post already made stays").

### 2.6. Giờ gợi ý của plan (suggested_post_at) được dùng ở đâu — và ở đâu không

`plans.suggested_post_at()` (`api/src/reels_api/plans.py:146-159`): ngày plan + vị trí trong ngày → giờ đăng của nhóm vào ngày đó, theo múi của nhóm. Trả None khi: ý tưởng ở Backlog, nhóm chưa có ngày bắt đầu, nhóm không có giờ đăng, hoặc giờ đó đã qua.

Được dùng ở:

- Nút Duyệt web (`ApproveVideoButton.tsx`): hẹn đúng giờ này.
- Tự duyệt (`auto_approve.py:52-68`): duyệt rồi đăng đúng giờ này; không có giờ gợi ý thì giữ lại (held) với lý do "Kế hoạch chưa có giờ đăng dự kiến cho video này, hoặc giờ đó đã qua".
- `schedule_video_at` (MCP): fallback khi không truyền `post_at`.
- Hiển thị: payload plan item (`plans.py:608`), payload video (`videos.py:1537, 1647, 1692, 1757`).

KHÔNG được dùng ở:

- Hàng chờ/worker (`page_queue.py`): không có một lần nhắc tới `suggested_post_at`.
- Nút Duyệt thuần (ReviewCard web, Telegram `ap:`, MCP `publish=none`): duyệt xong không hẹn gì cả.
- Nói cách khác: giờ gợi ý chỉ có hiệu lực khi đi đúng đường "duyệt + đăng theo plan". Đi đường hàng chờ thì giờ gợi ý bị bỏ qua hoàn toàn — đây là câu trả lời cho câu hỏi (2).

### 2.7. Hủy hẹn thì video đi đâu

- Hủy trên web: `POST /posts/{id}/take-down` (`routes_videos.py`, "Hủy đăng"/"Xóa"): nếu bài chưa tải lên Facebook (`remote_id` None) → Publication → `cancelled`, job publish đang chờ → `cancelled`. Video GIỮ nguyên trạng thái `approved`, KHÔNG về hàng chờ, KHÔNG về chờ duyệt. Sau đó có thể hẹn lại tay qua drawer Đăng bài (video đã duyệt nên qua được `ensure_approved`). Nếu bài đã tải lên Facebook rồi → enqueue job `unpublish` để hủy trên Facebook.
- Đã kiểm chứng live vụ 78 (27/11 00:35): hủy xong, video vẫn "Đã duyệt" + "Chờ đăng", không trong hàng chờ, không tự xếp lại.
- `unschedule_video` (MCP) chỉ gỡ khỏi hàng chờ, không hủy bài đã hẹn.
- `review.reject` không áp dụng cho video đã hẹn/đã đăng.

### 2.8. Không có cơ chế "giữ chỗ" khung cho lô dựng

Grep `reserv` trong `api/src` và `web/src` (main @472d4b0) không có kết quả nào liên quan đến giữ khung đăng. Một khung chỉ bị "chiếm" khi đã có Publication (đã hẹn) hoặc bài đã đăng. Hàng chờ không giữ chỗ; plan ngày mai cũng không giữ chỗ — plan chỉ là danh sách ý tưởng + giờ gợi ý, không tạo bản ghi nào trên lịch đăng. Vì vậy lô dựng 16:00 (dựng video cho ngày mai) không có gì bảo vệ 3 khung của ngày mai khỏi video lẻ vào hàng chờ trước.

## 3. Nguyên nhân gốc

Bốn nguyên nhân, theo thứ tự từ gần đến xa:

### 3.1. Một từ "Duyệt" che ba hành vi khác nhau

Cùng một nhãn, ở các kênh khác nhau:

- Chỉ duyệt: ReviewCard web, Telegram `ap:`, MCP `publish=none`.
- Duyệt + hẹn đúng giờ plan: ApproveVideoButton web, Tự duyệt, MCP `publish=schedule`.
- Duyệt + vào hàng chờ (worker tự xếp khung trống gần nhất): Telegram `qa:`, MCP `publish=queue` / `schedule_video`, nút "Thêm vào hàng chờ" web.

Người dùng bấm "Duyệt" không thể biết mình vừa làm (i), (ii) hay (iii) nếu không đọc kỹ từng màn hình. Quyết định 2026-11-12 cố ý gộp (ii) vào nút Duyệt trên plan tab ("nothing is scheduled without a member's tap" — đúng, vẫn cần một cú bấm; nhưng cú bấm đó đồng thời là duyệt và hẹn giờ). Quyết định review-gate 2026-11-26 ghi nhận: "The existing 'Duyệt' of the plan tab and 'Tự duyệt' are the same act plus a schedule" — tức hệ thống biết hai hành vi này đang gộp, và chấp nhận vì tiện cho luồng lô.

### 3.2. Hàng chờ không biết plan: "ai vào trước, lấy khung trước"

`fill()` chỉ biết thứ tự vào hàng và khung trống; không đọc `suggested_post_at`, không biết video nào thuộc ngày nào, không biết lô dựng 16:00 sắp ra video cho ngày mai. Video lẻ (78, không plan) và video lô (có plan) cạnh tranh cùng một hàng chờ, bình đẳng tuyệt đối. Video lẻ vào hàng lúc 00:08 thì lấy khung 28/11 07:00; video lô dựng lúc 16:00, duyệt lúc tối, lúc đó khung đã mất. Đây là câu trả lời cho câu hỏi (3).

### 3.3. Telegram tách hai bước nhưng bước hai là "đường thuận tiện duy nhất"

Sau khi duyệt, tin `offer_queue` hiện ngay nút "➕ Hàng chờ Già Mà Khỏe" — một cú bấm, không hiện khung sẽ xếp, không có nút "Chọn giờ khác" tại chỗ. Muốn chọn giờ phải rời Telegram, mở app, tìm video, mở drawer Đăng bài, chọn Hẹn giờ. Trong thực tế vận hành (duyệt nhanh trên điện thoại lúc nửa đêm), đường dễ nhất luôn thắng. Và nút Duyệt web (ApproveVideoButton) thì từ chối video không có plan, nên video lẻ như 78 gần như chỉ còn đường hàng chờ.

### 3.4. Không có trạng thái "Đã duyệt, chưa hẹn giờ" được nhìn thấy

Hệ thống có trạng thái này trên thực tế (review_status = approved, chưa có Publication), nhưng giao diện không tách nó ra: video chỉ hiện "Đã duyệt", không nói "chưa hẹn giờ" hay "đang chờ chọn giờ". Không có danh sách "đã duyệt mà chưa hẹn" để rà soát; slot-guard chỉ canh khung trống, không canh video đã duyệt mà chưa hẹn. Vì vậy video 78 sau khi hủy hẹn nằm ở "Chờ đăng" mà không ai nhắc phải hẹn lại — nó chỉ được phát hiện khi user tự mở lịch đăng.

## 4. Các app khác làm gì

Nguyên tắc chung rút ra từ 5 app: **giờ đăng luôn được chọn (hoặc hiện rõ) trước hoặc cùng lúc duyệt; không app nào để "duyệt" tự động lấy khung trống gần nhất mà không cho người duyệt thấy giờ đó.**

| App | "Duyệt" làm gì | Giờ đăng được chọn khi nào | Trạng thái "đã duyệt, chưa hẹn giờ" | Hàng chờ |
|---|---|---|---|---|
| **Buffer** | Hai nút riêng trong tab Approvals: "Approve and Schedule Post" (nếu đã đặt ngày giờ) hoặc "Approve and Add to Queue" (khung trống tiếp theo). Người duyệt thấy trước điều gì xảy ra. | Đặt trước khi duyệt (Schedule Post), hoặc lúc duyệt chọn vào hàng chờ. | Có: Drafts → Approvals → Queue/Scheduled, tách rõ. | Có: queue = khung trống tiếp theo trong lịch đăng của kênh; dùng cho nội dung không gấp giờ. |
| **Hootsuite** | Approval là quyền (Publish Message with Approval; người duyệt có quyền Approve Messages); có team duyệt, duyệt tuần tự/song song. | Bài được hẹn giờ TRƯỚC; khi duyệt xong, bài quay lại hàng chờ đã hẹn, giữ nguyên giờ. Duyệt không đổi giờ. | Có: pending approval queue riêng; bài bị từ chối vào rejected queue, không đăng. | Có: scheduled queue tách khỏi pending approval. |
| **Later** | Checkbox "Submit for Approval" trong Post Builder; Reviewer duyệt. | Hẹn giờ TRƯỚC (hoặc lưu nháp). Bài đã hẹn sẽ đăng đúng giờ "regardless of approval status"; nếu tắt "Publish Without Approval" thì chỉ được lưu nháp. | Có: trạng thái approval là cờ riêng trên bài đã hẹn giờ/nháp. | Lịch (calendar) là trung tâm; không có "lấy khung trống gần nhất" tự động. |
| **YouTube Studio** | Không có bước duyệt. | Người đăng chọn ngày + giờ + múi giờ cụ thể trong thẻ Schedule; có thể đổi giờ hoặc đăng ngay sau đó. | Tương đương: video Private (đã tải lên, chưa công khai) chờ giờ đã hẹn. | Không có. |
| **Meta Business Suite** | Không có bước duyệt tích hợp (ai có quyền đăng thì xếp lịch được). | Planner: chọn ngày giờ cụ thể cho từng bài; có lưu nháp. | Có: Drafts tách khỏi Scheduled trong Planner. | Không có hàng chờ tự lấp; mọi bài đều có giờ cụ thể. |

Nguồn (truy cập 27/11/2026):

- Buffer — "Managing and approving draft posts", support.buffer.com: https://support.buffer.com/en-us/articles/managing-and-approving-draft-posts-57li7M8tDA
- Hootsuite — "Set up an approval process", help.hootsuite.com: https://help.hootsuite.com/s/article/set-up-approvals ; "Prescreen integration", developer.hootsuite.com: https://developer.hootsuite.com/v1.0/docs/prescreen-integration (mục: bài được duyệt "moves back into the scheduled queue (if it's been scheduled)").
- Later — "Team Collaboration and Content Approvals", help.later.com: https://help.later.com/hc/en-us/articles/40954654500375-Team-Collaboration-and-Content-Approvals
- YouTube Studio — "Schedule video publish time", support.google.com: https://support.google.com/youtube/answer/1270709
- Meta Business Suite — "Meta Business Suite has no approval step…", OctoSpark: https://staging.octospark.ai/facebook-post-scheduler/ ; quy trình draft → duyệt → xếp lịch trong Planner, Dorobanți Media: https://www.dorobantimedia.com/en/blog/meta-business-suite-ai-content-workflow

Điểm chung đáng chú ý: **Buffer là app duy nhất trong 5 app có "hàng chờ lấy khung trống tiếp theo" — và chính Buffer là app tách rõ nhất hai nút ở lúc duyệt** ("Approve and Schedule Post" vs "Approve and Add to Queue"). Tức là ngay cả khi có queue, người duyệt vẫn được chọn và thấy trước. Hootsuite và Later thì đi hướng ngược lại: giờ được chọn trước, duyệt chỉ là cái gật đầu, không động vào giờ.

## 5. Phương án sửa tận gốc

Xếp theo mức độ can thiệp tăng dần. Mọi phương án đều giữ được nhịp 3 video/ngày/page và lô dựng 16:00, trừ khi ghi chú khác. "Giữ nhịp" ở đây nghĩa là: lô 16:00 vẫn dựng 3 video Già + 3 video Ăn Lành cho ngày mai, user vẫn duyệt nhanh được, không thêm quá 1 cú bấm cho mỗi video lô.

### P0 — Luật vận hành, không sửa code (làm ngay tối nay)

- Video lẻ không có plan: duyệt xong KHÔNG bấm "Hàng chờ" trên Telegram; mở app → Đăng bài → Hẹn giờ tay (giờ cụ thể, tránh khung của lô dựng).
- Video lô: duyệt bằng nút Duyệt web (đúng giờ plan) hoặc approve_video publish=schedule với giờ gợi ý; không đưa video lô vào hàng chờ.
- Thay đổi: không có. Rủi ro: dựa vào trí nhớ con người; chỉ cần một lần bấm nhầm là lặp lại vụ 78. Đây là băng tạm, không phải sửa gốc.

### P1 — Hiện giờ trước khi xếp + đổi nhãn nút (1 PR nhỏ, ít rủi ro nhất)

**P1a — Telegram `offer_queue` hiện khung sẽ xếp.** Khi gửi tin "Thêm vào hàng chờ?", tính `free_slots()` ngay lúc đó (hàm đã có, `list_my_pages` cũng trả `free_slots`) và ghi rõ: "Thêm vào hàng chờ của Già Mà Khỏe? Video sẽ đăng vào khung trống tiếp theo: Thứ 7 28/11 07:00." Kèm nút thứ hai "Chọn giờ khác" (mở app tới drawer Đăng bài của video). Thay đổi: `api/src/reels_api/telegram_commands.py:286-297` (`offer_queue`) + `page_queue.free_slots`. Rủi ro: khung hiện lúc gửi tin có thể đổi trước khi bấm (ai đó xếp trước trong 60 giây) — tin nhắn nên ghi "khung trống lúc này" và worker vẫn xếp khung trống thật lúc chạy; nếu khác, gửi tin báo giờ thật sau khi xếp.

**P1b — Đổi nhãn hai nút Duyệt trên web cho khớp hành vi.** ReviewCard "✓ Duyệt" → "✓ Duyệt (chưa hẹn giờ)"; ApproveVideoButton "Duyệt" → "Duyệt & đăng lúc {giờ gợi ý}" (giờ đã có sẵn trong Popconfirm, chỉ cần đưa ra nút ngoài). Thay đổi: `web/src/components/video/ReviewCard.tsx:114-117`, `web/src/components/actions/ApproveVideoButton.tsx`. Rủi ro: gần như không có; chỉ là chữ.

**P1c — MCP: ghi rõ trong mô tả tool.** `approve_video` publish=queue và `schedule_video`: thêm câu "sẽ xếp vào khung trống tiếp theo của Page (không theo giờ gợi ý của plan)". Thay đổi: `api/src/reels_api/mcp_server.py` (docstring). Rủi ro: không có.

Giữ nhịp: có. P1 không đổi luồng, chỉ làm rõ.

### P2 — Hàng chờ tôn trọng giờ plan (sửa luật xếp khung)

**Luật mới trong `fill()` / `_fill_page()` (`api/src/reels_api/page_queue.py:114-165`):**

1. Video trong hàng chờ mà có `suggested_post_at` trong cửa sổ 48h và khung đó còn trống → hẹn đúng giờ đó (thay vì khung trống đầu tiên).
2. Video KHÔNG có giờ gợi ý (như 78) → khi chọn khung, bỏ qua các khung mà một ý tưởng plan khác (cùng nhóm) đã "đặt trước" bằng giờ gợi ý của nó — trừ khi khung đó là giờ gợi ý của chính video này. Nói cách khác, plan ngày mai giữ chỗ mềm cho video của nó.
3. Nếu giờ gợi ý đã qua hoặc khung đã có người → rơi về luật cũ (khung trống gần nhất).

Thay đổi: `page_queue.py` (`free_slots` cần thêm tham số "khung được bảo vệ bởi plan", hoặc `_fill_page` lọc slot theo plan) + đọc `plans.suggested_post_at` cho các plan item của nhóm. Cần test: `api/tests/test_page_queue.py` đã có, bổ sung case video có plan / video lẻ / khung plan đã có người.

Rủi ro: trung bình. (a) Nếu lô dựng chết im (không ra video), khung plan bị "giữ mềm" mà không ai dùng → khung trống, slot-guard đã có cảnh báo "chưa dựng" (job rs-slot-guard-30m v2) nên vẫn phát hiện được; nhưng video lẻ muốn dùng khung đó sẽ bị đẩy sang khung sau — cần quy tắc hết hạn: chỉ bảo vệ khung của plan item có ngày là hôm nay/ngày mai và video của nó chưa được duyệt, hoặc chỉ bảo vệ tới giờ dựng của nhóm + 2 giờ. (b) Hai video cùng giờ gợi ý (trùng plan) → ai vào hàng trước lấy trước, người sau rơi về khung trống gần nhất — cần ghi rõ trong thông báo sau khi xếp.

Giữ nhịp: có, và khớp hơn — video lô duyệt muộn vẫn về đúng giờ plan của nó thay vì bị đẩy sang ngày sau.

### P3 — Giữ chỗ cứng cho lô dựng (KHÔNG khuyến nghị làm ngay)

Khi job dựng 16:00 tạo video cho ngày mai, tạo luôn bản ghi "giữ chỗ" cho 3 khung của ngày đó (hoặc tạo Publication ở trạng thái giữ chỗ), hết hạn nếu video không được duyệt trước giờ đăng X giờ; video lẻ vào hàng chờ sẽ bỏ qua khung đã giữ. Thay đổi: cần thêm trạng thái/bảng giữ chỗ + TTL + dọn dẹp + hiển thị "Đã giữ chỗ" trên Lịch đăng; chạm `page_queue.py`, `videos.py` (lúc tạo video), worker, và UI lịch. Rủi ro: cao — khung bị khóa oan khi video lỗi/render lại (re-render trả video về pending + hủy lịch, nhưng giữ chỗ thì sao?); thêm một trạng thái mới là thêm một lớp lỗi mới; lợi ích so với P2 không nhiều vì P2 đã dùng plan làm "giữ chỗ mềm". Chỉ cân nhắc nếu P2 chứng minh không đủ (ví dụ plan thường xuyên thay đổi sau 16:00).

### P4 — Tách "Duyệt" khỏi "Hẹn giờ" trên mọi kênh (sửa tận gốc, đích đến — mô hình Buffer)

**Mô hình mới:**

1. Mọi nút "Duyệt" (web ReviewCard, Telegram `ap:`, MCP `publish=none`) chỉ chuyển video sang trạng thái "Đã duyệt, chưa hẹn giờ" — hiển thị riêng trên danh sách video và trang Lịch đăng (badge "Đã duyệt · Chưa hẹn giờ"), có danh sách rà soát riêng.
2. Hẹn giờ là bước riêng, với 3 lựa chọn hiện rõ cùng lúc (như Buffer): (1) "Đúng giờ gợi ý của plan — {ngày giờ}" (chỉ hiện khi có suggested_post_at; mặc định chọn nếu có); (2) "Chọn giờ khác" (datetime-local, như drawer Đăng bài hiện tại); (3) "Vào hàng chờ — lấy khung trống tiếp theo (dự kiến {khung})".
3. Nút Duyệt web (ApproveVideoButton) đổi thành hai bước: bấm Duyệt → hiện 3 lựa chọn hẹn giờ (giờ gợi ý đã điền sẵn) → xác nhận. Trên Telegram: sau khi duyệt, tin `offer_queue` thành tin chọn giờ với 3 nút (giờ gợi ý / chọn giờ khác mở app / hàng chờ + khung dự kiến). Trên MCP: `approve_video` mặc định vẫn `none`; hẹn giờ qua `schedule_video_at` (giờ gợi ý/chọn tay) hoặc `schedule_video` (hàng chờ) — đã có đủ tool, chỉ cần đổi luật gọi trong job/chat.
4. Cảnh báo lệch giờ (đi kèm P4, có thể tách ra làm P2b): khi video được xếp vào khung khác ngày/giờ gợi ý của plan (hoặc khi worker xếp video có plan lệch khỏi giờ gợi ý), ghi `video_events` + gửi tin Telegram/WhatsApp "Video X (plan 28/11 07:00) sẽ đăng 29/11 07:00". Thay đổi: `page_queue._fill_page` so sánh slot với suggested_post_at; cần định nghĩa "lệch" (khác ngày, hoặc lệch > 1 khung).

Thay đổi: `ReviewCard.tsx` + `ApproveVideoButton.tsx` (tách bước), `telegram.py`/`telegram_commands.py` (tin chọn giờ), `page_queue.py` (luật P2 làm nền), UI danh sách/lịch (badge trạng thái mới), test e2e `web/e2e/queue.spec.ts` + `api/tests/test_page_queue.py` + `test_telegram.py`. Rủi ro: trung bình–cao do chạm nhiều mặt; nhưng mỗi mặt đổi nhỏ và có test sẵn. Cần làm theo từng kênh (web → Telegram → MCP) thay vì một PR lớn.

Giữ nhịp: có — video lô vẫn duyệt + hẹn đúng giờ plan trong 2 cú bấm (bấm Duyệt → xác nhận giờ gợi ý đã điền sẵn); video lẻ vẫn có đường hàng chờ nhưng phải thấy khung trước khi chọn. Nhịp 3 video/ngày/page không đổi; lô 16:00 không đổi.

## 6. Khuyến nghị

**Khuyến nghị chính: làm P4 theo hai bước — bước 1 ngay (P1 + P2), bước 2 sau (P4 đầy đủ). Không làm P3.**

- **Bước 1 (1–2 PR nhỏ, làm ngay): P1a + P1b + P1c và P2.** Lý do: P1 hết "bất ngờ" ngay trong tuần (người bấm thấy khung trước khi xếp; hai nút Duyệt không còn cùng nhãn); P2 sửa đúng chỗ gây ra vụ 78 — hàng chờ tôn trọng plan — mà không đổi giao diện hay thêm trạng thái mới. Cả hai đều có test sẵn (`test_page_queue.py`, `test_telegram.py`) và không động vào luồng đăng bài.
- **Bước 2 (1 PR theo từng kênh): P4 đầy đủ + cảnh báo lệch giờ.** Lý do: đây mới là sửa tận gốc — "duyệt" và "hẹn giờ" thành hai bước riêng trên mọi kênh, giống Buffer (app duy nhất trong 5 app khảo sát có cả hàng chờ lẫn duyệt tách bạch). Sau P4, vụ 78 không thể lặp lại dưới dạng "bấm Duyệt rồi video tự chạy đi đâu không biết", vì mọi đường hẹn giờ đều hiện giờ trước khi xác nhận.
- **Không làm P3** (giữ chỗ cứng): chi phí cao, thêm trạng thái mới dễ sinh lỗi, mà P2 đã đạt ~80% lợi ích của nó bằng "giữ chỗ mềm" từ plan. Chỉ xem lại P3 nếu sau P2 vẫn còn video lẻ chiếm khung của lô dựng.
- **P0 áp dụng ngay tối nay** (luật tay): video lẻ không plan thì duyệt xong hẹn tay qua Đăng bài, không bấm Hàng chờ trên Telegram — cho tới khi P1a lên.

**Bước tiếp theo đề xuất:**

1. User chốt: đồng ý bước 1 (P1 + P2) và đích P4, hay chỉ muốn bước 1 trước.
2. Viết brief cho coder từ báo cáo này (file này đã đủ chi tiết để làm brief kỹ thuật cho bước 1; bước 2 cần thêm quyết định về nhãn nút và tin Telegram).
3. Sau khi P1a + P2 lên: kiểm chứng bằng vụ thử — duyệt một video lẻ qua Telegram, xem tin offer_queue có hiện khung không; duyệt một video lô, xem nó có về đúng giờ plan không khi khung đó đang trống.

## Phụ lục A — Trích dẫn code chính (main @ 472d4b0)

| Vấn đề | File | Dòng / hàm |
|---|---|---|
| Duyệt chỉ đổi trạng thái | `api/src/reels_api/review.py` | `approve()` 137–164; `reject()` 166–177; `ensure_approved()` 227 |
| Route Duyệt web (chỉ duyệt) | `api/src/reels_api/routes_review.py` | `approve()` 32–40 |
| Nút "✓ Duyệt" (chỉ duyệt) | `web/src/components/video/ReviewCard.tsx` | 46–58 ("Vẫn duyệt"), 114–117 |
| Nút "Duyệt" (duyệt + hẹn giờ plan) | `web/src/components/actions/ApproveVideoButton.tsx` | `approve()` đọc `suggested_post_at`; `send()` duyệt rồi publish đúng giờ đó; Popconfirm "Duyệt đăng lúc …?" |
| Drawer Đăng bài (hẹn tay) | `web/src/components/video/PublishCard.tsx` | 128, 185–191 ("Đăng ngay" / "Hẹn giờ") |
| Hẹn/đăng (yêu cầu đã duyệt) | `api/src/reels_api/routes_videos.py` | hàm `publish` (giờ hẹn 15'–29 ngày); `take_down` "Hủy đăng" — bài chưa lên FB thì Publication → cancelled, video giữ `approved` |
| MCP approve 4 chế độ | `api/src/reels_api/mcp_server.py` | `approve_video` 615–655; `schedule_video_at` 835–855; `unschedule_video` 868–880; `schedule_video` 2933–2945 |
| Hàng chờ + lấp khung | `api/src/reels_api/page_queue.py` | Hằng số 33–38 (48h/30'/30'/100); `post_times()` 41; `free_slots()` 57; `fill()` 114; `_fill_page()` 137; `fill_due()` 167 |
| Route hàng chờ | `api/src/reels_api/routes_queue.py` | `add()` "Thêm vào hàng chờ"; `remove()` "Bỏ khỏi hàng chờ"; `_page_for()` (suy ra Page theo nhóm) |
| Worker gọi lấp khung | `api/src/reels_api/worker.py` | `POST_CHECK_SECONDS = 60.0` (53); `serve()` 185–193 |
| Telegram Duyệt + offer hàng chờ | `api/src/reels_api/telegram.py` | `_buttons()` 294; `_button()` 316 (duyệt ở 347 rồi gọi `offer_queue`) |
| Telegram /cho_duyet + nút hàng chờ | `api/src/reels_api/telegram_commands.py` | `pending()` 110; `offer_queue()` 286; `button()` 340 (`rv:` xem video, `qa:` thêm vào hàng chờ) |
| Giờ gợi ý của plan | `api/src/reels_api/plans.py` | `suggested_post_at()` 146–159 |
| Tự duyệt (duyệt + đăng giờ plan) | `api/src/reels_api/auto_approve.py` | 52–68; `_blocker()` (không có giờ gợi ý → held) |
| Quyết định liên quan | `docs/decisions/` | 2026-11-12-plan-approve-button.md; 2026-11-26-review-gate.md; 2026-11-26-schedule-timezone.md; 2026-11-26-telegram-commands.md |

## Phụ lục B — Những gì chưa xác minh được

1. **Chuỗi bấm chính xác của vụ 78.** Code cho thấy đường Telegram là: Duyệt (`ap:`) → tin offer_queue → "➕ Hàng chờ" (`qa:`) → worker xếp lịch trong 60 giây. Đường web Duyệt (ApproveVideoButton) bị loại vì 78 không có giờ gợi ý nên nút này từ chối. Đường MCP `approve_video publish=queue` cũng có thể làm điều tương tự, nhưng không có lệnh nào như vậy từ chat chính trong khung 00:07–00:20. Không có log thao tác (video_events chỉ ghi trạng thái, không ghi từng cú bấm Telegram) để khẳng định tuyệt đối ai bấm nút hàng chờ lúc nào — chỉ biết publication 761 do NamTC tạo.
2. **Hành vi worker khi hai video cùng tranh một khung.** `fill()` lấy video đầu hàng chờ đi được; video sau lấy khung sau. Chưa kiểm chứng live trường hợp hai video cùng giờ gợi ý.
3. **Tin offer_queue trên Telegram thực tế hiện chữ gì.** Trích dẫn trong báo cáo là từ code (`telegram_commands.py:286-297`); chưa chụp màn hình tin thật của vụ 78 để đối chiếu từng chữ.
4. **Các app ngoài:** chỉ tra cứu tài liệu công khai ngày 27/11/2026, không có tài khoản trả phí để bấm thử (đặc biệt Hootsuite chỉ rõ gói Advanced/Enterprise mới có approval; Buffer chỉ rõ Team plan mới có duyệt draft). Tính năng có thể khác theo gói/region.

---
*Báo cáo này chỉ phân tích và đề xuất. Không sửa code, không đổi job/cron, không duyệt/hẹn/xóa video nào.*
