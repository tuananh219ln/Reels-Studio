# Brief Reels Studio — Mẫu dựng, thiết lập mặc định và quyền sở hữu theo người dùng

> **Việc MỚI, brief riêng** — user chốt sáng 09/11/2026. Không
> thuộc brief "Bán tự động dựng & đăng video hằng ngày"
> (docs/specs/semi-auto-posting/brief.md) — brief đó đã xong.
>
> Nguyên tắc xuyên suốt: (1) **thiết lập theo tài khoản (theo
> người dùng)** — bỏ tầng team trong công tắc mẫu dựng và trong
> thiết lập mặc định; (2) **mẫu dựng có tầng nhóm chủ đề** phía
> trên tầng tài khoản; (3) **những gì một user tạo thì user khác
> không được xoá**. Mẫu dựng cá nhân, mẫu theo nhóm chủ đề và
> thiết lập mặc định cá nhân là các thiết lập **tách biệt** —
> không gộp, không lồng nhau; việc này xử lý tất cả theo các
> nguyên tắc trên.
>
> Sáu phần: Phần 1 — công tắc tự áp mẫu theo tài khoản; Phần 2 —
> mẫu dựng theo nhóm chủ đề; Phần 3 — thiết lập mặc định theo tài
> khoản; Phần 4 — quyền sở hữu khi xoá; Phần 5 — mở mẫu dựng ra
> MCP để agent dựng video xem, chọn và lưu được mẫu; Phần 6 —
> drawer ngày ở tab Kế hoạch: bấm ra ngoài để đóng. Làm theo thứ
> tự Phần 1 → 2 → 3 → 4 → 5 → 6 trên cùng đợt, các phần sau
> không chặn các phần trước.
>
> Thi công theo lệ team: đọc AGENTS.md + docs/decisions.md trước
> (kèm quy ước ghi quyết định MỚI ở mục ngay dưới đây); làm trên
> **nhánh mới** `feat/per-user-settings-ownership` tạo từ main
> (tách PR theo từng Phần nếu thấy gọn hơn); TDD, test bằng fake
> services, báo cáo 3 phần, không tự merge.

## Quy ước ghi quyết định (MỚI — user báo sáng 09/11/2026)

Quy ước đọc tài liệu trước khi làm **đã thay đổi** ở nửa sau:

- Đọc trước khi làm: giữ nguyên — đọc AGENTS.md và
  docs/decisions.md, **kèm các file quyết định riêng** đã tạo
  trong docs/ theo quy ước mới (nếu có).
- **Ghi quyết định mới: KHÔNG append vào docs/decisions.md
  nữa.** Khi việc trong đợt này sinh ra hoặc thay đổi một quyết
  định, tạo **một file quyết định riêng trong docs/** cho quyết
  định đó (đặt trong thư mục `docs/decisions/` nếu repo đã có
  thư mục này; chưa có thì tạo thư mục đó), gồm: ngày, quyết
  định, lý do ngắn; nếu thay thế một quyết định cũ trong
  docs/decisions.md thì ghi rõ "thay thế mục <ngày — tiêu đề>"
  trong file mới, không sửa nội dung mục cũ.
- Lưu ý đối chiếu: tại thời điểm viết brief, bản AGENTS.md và
  đầu file docs/decisions.md trong working copy vẫn mô tả quy
  ước cũ (append vào decisions.md). Nếu lúc thi công repo vẫn
  vậy, cứ theo quy ước MỚI trong mục này cho các quyết định phát
  sinh từ đợt việc này, và **ghi rõ sự lệch này trong báo cáo**
  để user quyết việc cập nhật AGENTS.md riêng — không tự sửa
  AGENTS.md trong đợt này.

## Ghi chú thuật ngữ (đọc trước)

- **Theo tài khoản (theo người dùng):** mỗi tài khoản đăng nhập
  tương ứng với một người dùng trong team. Mọi chỗ trong brief
  ghi "riêng của tài khoản" / "theo tài khoản" đều hiểu là riêng
  của **người dùng** sở hữu tài khoản đó — không dùng chung, người
  dùng khác không thấy để sửa và không bị áp dụng.
- **Nhóm chủ đề** là KnowledgeTopic (ví dụ "Ăn Lành Sống Khỏe –
  Sức khỏe") — **khác với nhóm/team** là tập hợp các người dùng
  dùng chung tool. Brief này bỏ tầng team trong thiết lập; tầng
  nhóm chủ đề trong mẫu dựng thì giữ (Phần 2).
- **Trên giao diện:** các trang thiết lập cá nhân (Mẫu dựng, Thiết
  lập mặc định) phải ghi nhãn/ghi chú rõ ràng dạng "Thiết lập
  riêng của tài khoản (theo người dùng)" ở ngay khu vực thiết lập,
  để người dùng không nhầm với thiết lập chung của team.

## Bối cảnh và hiện trạng (kiểm chứng trong code, 07–09/11)

Đã đọc `routes_templates.py`, `autoedit.py`, và kiểm chứng cơ chế
thiết lập mặc định hiện tại:

- Ô "Mẫu cho video mới" ở trang Cấu hình › Mẫu dựng
  (`/settings/templates`) lưu ở **AppSetting toàn cục**, key
  `edit_template_default` — một giá trị duy nhất cho cả team, thành
  viên nào đăng nhập cũng bật/tắt/đổi được.
- `autoedit.apply_default` áp mẫu đó cho **mọi video mới** ngay khi
  cảnh được viết xong, không phân biệt người tạo — gồm cả video
  tạo trên web, tạo từ kế hoạch và tạo qua MCP.
- Hệ quả nếu ai đó bật mẫu "Gợi ý của app": chuyển cảnh của video
  mới bị ghi đè xoay vòng zoom/slide/fade/wipe, mỗi cảnh nội dung
  thêm tiếng whoosh, cảnh tiêu đề thêm tiếng rise, cảnh cuối bị
  gắn thêm lớp chữ "Lưu video lại để xem sau nhé!" — lệch chuẩn
  dựng đã khoá của các page và xung đột với cảnh kết CTA bắt buộc
  của kịch bản. (Mẫu không đổi nội dung kịch bản: chữ trên hình,
  lời đọc, thứ tự cảnh, caption, hashtag giữ nguyên.)
- Tool **chưa có preset trình bày theo nhóm chủ đề**: thiết lập
  trình bày chỉ có ở từng video (sao từ mặc định của user/team);
  KnowledgeTopic có prompt viết kịch bản, prompt nhân bản, từ cấm
  và giọng riêng nhưng không có mẫu dựng. Một tài khoản chạy nhiều
  page/chủ đề với chuẩn dựng khác nhau (2 page của user là ví dụ)
  hiện phải chỉnh tay từng video.
- Trang Cài đặt › Thiết lập mặc định hiện có **hai tầng**: mặc
  định của người dùng ("Của tôi") và mặc định của nhóm/team ("Của
  nhóm"); video mới khởi tạo từ mặc định của người tạo, ai chưa có
  mặc định riêng thì ăn mặc định của nhóm — tức thiết lập của
  người khác vẫn chạm được vào video của mình.
- Quyền xoá hiện không theo chủ sở hữu: các đối tượng trong tool
  phần lớn chưa kiểm tra người tạo khi xoá (kiểm chứng code
  02/11: sản phẩm affiliate có `created_by` nhưng lúc gắn/liệt kê
  không kiểm quyền; Fanpage đã có `owner_id` từ 08/11). User này
  xoá được đồ của user khác là rủi ro thật khi team dùng chung.
- Production: công tắc mẫu đang để "Không áp mẫu nào" (default =
  null, kiểm chứng 09/11 00:45) nên chưa có tác động — đây là lúc
  đổi cơ chế an toàn nhất. Trong lúc chờ thi công, job dựng video
  mỗi sáng qua MCP (rs-mcp-morning-build) có bước gác: kiểm tra
  công tắc ở đầu mỗi lượt, thấy mẫu đang bật thì dừng toàn bộ
  lượt chạy.

## Phần 1 — Công tắc tự áp mẫu theo từng tài khoản

- **Lưu theo từng người dùng.** Chuyển giá trị của công tắc từ
  AppSetting toàn cục sang giá trị riêng của từng user. Cách lưu
  cụ thể (key có hậu tố user, bảng/cột riêng…) chọn theo kiến
  trúc hiện tại và nêu rõ trong báo cáo.
- **Trang Mẫu dựng:** ô "Mẫu cho video mới" hiển thị và lưu lựa
  chọn của **chính người đang đăng nhập**, ghi nhãn "Của tôi (theo
  người dùng)" theo mục Ghi chú thuật ngữ. User chưa từng chọn
  thì giá trị là "Không áp mẫu nào". Giá trị này là mẫu mặc định
  của **tài khoản** — một tầng trong chuỗi ưu tiên ở Phần 2.
- **Điểm áp mẫu:** `autoedit.apply_default` và mọi nơi gọi nó lấy
  mẫu theo **người tạo video** (user sở hữu phiên tạo — đường web,
  đường tạo từ kế hoạch, đường MCP đều mang tài khoản của user
  tạo) và theo **nhóm chủ đề của video** (Phần 2). Video của user
  A không bao giờ ăn mẫu mặc định tài khoản của user B. Đường tạo
  nào không xác định được người tạo (job nền/hệ thống) thì
  **không áp mẫu** — mặc định an toàn là null.
- **Ràng buộc cứng với cảnh kết CTA:** kịch bản của user luôn có
  cảnh kết CTA bắt buộc viết riêng theo từng video. Lớp chữ cuối
  của mẫu **không được** chen sau cảnh kết CTA và không ghi đè
  cảnh kết: nếu video đã có cảnh kết CTA và mẫu có lớp cuối, bỏ
  qua lớp cuối của mẫu (giữ CTA), các thành phần còn lại của mẫu
  vẫn áp bình thường. Áp dụng cho mọi đường áp mẫu (tự áp theo
  chuỗi ưu tiên, áp tay trên web, áp qua MCP ở Phần 5). Nêu rõ
  hành vi trong báo cáo và có test phủ.
- **API:** `GET /api/edit-templates` — trường `default` trả theo
  user đang đăng nhập; các thao tác đặt/xoá mẫu mặc định chỉ tác
  động bản ghi của chính user đó.
- **Migration:** giá trị toàn cục hiện tại đang là null → khởi tạo
  mọi user là "Không áp mẫu nào". Sau khi chuyển, không còn đường
  đọc nào dùng key toàn cục cũ nữa (xoá key hoặc để lại nhưng
  không đọc — nêu rõ cách xử lý trong báo cáo).

## Phần 2 — Mẫu dựng theo nhóm chủ đề (một nhóm nhiều mẫu)

- **Mẫu theo nhóm:** mỗi nhóm chủ đề gắn được **nhiều mẫu** (quan
  hệ nhóm ↔ mẫu theo kiến trúc hiện tại — bảng liên kết hoặc tương
  đương) và chỉ định **một mẫu mặc định của nhóm** (có thể để
  trống = nhóm không áp mẫu). Chọn/gắn mẫu ngay tại trang Kho
  kiến thức của nhóm, cạnh phần prompt, từ cấm và giọng của nhóm.
- **Điểm áp:** khi tạo video thuộc một nhóm, nếu video chưa được
  chọn mẫu riêng và nhóm có mẫu mặc định thì áp mẫu của nhóm, qua
  cùng cơ chế áp mẫu của Phần 1 (mở rộng để nhận nguồn mẫu theo
  chuỗi ưu tiên). Đường tạo từ kế hoạch và đường MCP cũng phải
  tôn trọng mẫu của nhóm như đường web.
- **Chuỗi ưu tiên đầy đủ khi áp mẫu cho video mới:** mẫu chọn
  riêng trên video › mẫu mặc định của nhóm chủ đề › mẫu mặc định
  của tài khoản người tạo (Phần 1) › không áp mẫu.
- Mẫu gắn cho nhóm lấy từ thư viện mẫu hiện có (lưu mẫu từ một
  video như hiện tại); việc này không tự tạo nội dung mẫu mới.

## Phần 3 — Thiết lập mặc định theo tài khoản (bỏ tầng nhóm/team)

- **Bỏ tầng nhóm/team:** từ nay video mới chỉ khởi tạo từ **thiết
  lập mặc định cá nhân của người tạo video**. Không còn đường đọc
  nào lấy mặc định "của nhóm" để khởi tạo video nữa — sửa mặc
  định nhóm (nếu dữ liệu còn tồn tại) không được tác động tới bất
  kỳ video mới nào.
- **Giao diện:** trang Cài đặt › Thiết lập mặc định chỉ còn phần
  của tài khoản đang đăng nhập, ghi nhãn "Của tôi (theo người
  dùng)"; bỏ phần "Của nhóm" khỏi giao diện. Các trường trong bộ
  thiết lập (giọng, nhạc nền, màu đánh dấu, dạng chữ, preset và cỡ
  chữ tiêu đề, chuyển cảnh, tốc độ, âm lượng…) giữ nguyên — chỉ
  đổi phạm vi áp dụng.
- **User chưa có mặc định cá nhân:** vẫn tạo được video; bộ khởi
  tạo là mặc định gốc của hệ thống (built-in), không phải mặc
  định của nhóm hay của user khác.
- **Migration:** tại thời điểm chuyển, user nào chưa có mặc định
  cá nhân thì khởi tạo mặc định cá nhân cho họ bằng **bản sao của
  mặc định nhóm hiện tại**, để hành vi tạo video không đổi đột
  ngột; sau thời điểm đó mặc định nhóm không còn tác động gì nữa.
  Cách xử lý dữ liệu mặc định nhóm cũ (xoá hay giữ nhưng không
  đọc) nêu rõ trong báo cáo.
- **Áp cho mọi đường tạo video:** web, tạo từ kế hoạch, nhân bản
  (giữ thiết lập của video gốc như hiện tại) và MCP — tạo bằng
  tài khoản nào thì khởi tạo theo mặc định cá nhân của tài khoản
  đó.

## Phần 4 — Quyền sở hữu khi xoá: user khác không được xoá

Nguyên tắc: **đối tượng do user nào tạo thì chỉ user đó (chủ sở
hữu) mới được xoá.** User khác không xoá được — giao diện ẩn/vô
hiệu thao tác xoá, API trả lỗi từ chối (403) nếu cố gọi. Việc này
chỉ siết quyền **xoá**; quyền xem và sử dụng chung giữ như hiện
tại, quyền sửa giữ như hiện tại trừ các mục đã có quy định riêng
trong các phần trên.

Các loại đối tượng áp dụng (kiểm kê lại khi thi công; loại nào
chưa có trường người tạo/chủ sở hữu thì bổ sung — các trường đã
biết: video và sản phẩm affiliate có người tạo, Fanpage có
`owner_id`):

- Video — kèm cảnh, file render, các bản nhân bản và bản TikTok
  đi theo video.
- Nhóm chủ đề — kèm prompt viết kịch bản, prompt nhân bản và từ
  cấm của nhóm.
- Kế hoạch 30 ngày của một nhóm chủ đề và từng ý tưởng trong kế
  hoạch (kể cả ý tưởng ở Backlog).
- Mẫu dựng cá nhân (mẫu user tự lưu) và mẫu mặc định cá nhân.
- Sản phẩm affiliate user đã thêm vào tool.
- Ảnh/clip trong thư viện tư liệu do user tải lên.
- Bài nhạc user tải lên thư viện nhạc.
- Fanpage user đã nhận sở hữu — user khác không gỡ liên kết,
  không xoá page khỏi tool; lịch đăng và cấu hình đăng của page
  đi theo quyền của chủ page.
- Bản ghi bài đã đăng và số liệu của bài (xoá là mất mốc đo 48h
  và số liệu KPI).
- Chuỗi tự động (auto run) user đã cấu hình.
- Thiết lập mặc định cá nhân — user khác không xoá/reset hộ.
- Kết nối tài khoản riêng của user (TikTok, Shopee…) — user khác
  không ngắt kết nối.

Quy tắc kèm theo:

- **Xoá đối tượng cha:** xoá nhóm chủ đề / video kéo theo các đối
  tượng con như hiện tại, nhưng nếu bên trong còn đối tượng con
  **do user khác tạo** (ví dụ nhóm chủ đề của A nhưng B đã tạo
  video trong nhóm đó) thì **chặn xoá** và báo rõ lý do, tránh
  xoá lây đồ của người khác.
- **Qua MCP cũng vậy:** các thao tác xoá qua MCP (ví dụ xoá cảnh
  của một video) chỉ thực hiện được trên đối tượng thuộc user sở
  hữu kết nối MCP đó.
- **Ngoại lệ admin:** mặc định thi công là **không có ngoại lệ**
  — admin cũng không xoá hộ đồ của user khác. (User chưa chốt
  khác; nếu đổi ý thì cập nhật brief này trước khi thi công phần
  này.)

## Phần 5 — Mẫu dựng qua MCP: xem, chọn và lưu mẫu

Hiện trạng (kiểm chứng 09/11): MCP có 41 tool, **không có tool nào
về mẫu dựng** — agent dựng video (job mỗi sáng) không xem được kho
mẫu, không áp mẫu cho một video cụ thể, không lưu mẫu mới. Mẫu
hiện chỉ thao tác được trên web, trong khi đường sản xuất chính
của user chạy qua MCP.

Thêm 3 tool MCP, bám mẫu `set_video_options` đã có (validate
trước, sai thì không lưu gì; scope `reels:read` cho tool xem,
`reels:write` cho tool áp/lưu):

- **Xem kho mẫu** (`list_templates` — tên gợi ý): liệt kê các mẫu
  trong phạm vi của user gọi: mẫu cá nhân của user và mẫu gắn với
  các nhóm chủ đề (Phần 2). Mỗi mẫu trả: id, tên, phạm vi (cá nhân
  / nhóm nào), tóm tắt thành phần đủ để chọn mà không mở web —
  kiểu chuyển cảnh, có hiệu ứng tiếng từng cảnh không, có lớp chữ
  cuối không, và dạng video hợp (slides / xuyên suốt) nếu suy ra
  được từ mẫu.
- **Áp mẫu cho một video** (`apply_template_to_video` — tên gợi
  ý): áp một mẫu cho một video cụ thể, dùng lại đúng logic áp mẫu
  thủ công trên web. Đây chính là tầng "mẫu chọn riêng trên video"
  — cao nhất trong chuỗi ưu tiên ở Phần 2. Áp sau khi cảnh đã viết
  xong, trước render. Gọi lại với mẫu khác: hành vi thay mẫu (có
  dọn sạch thành phần của mẫu trước hay không) theo đúng khả năng
  của logic áp mẫu hiện tại và phải nêu rõ trong báo cáo.
- **Lưu video thành mẫu cá nhân** (`save_video_as_template` — tên
  gợi ý): lưu phần trình bày hiện tại của một video thành mẫu mới
  trong kho **cá nhân** của user gọi, kèm tên mẫu do người gọi
  truyền. Trùng tên với mẫu cá nhân đã có → từ chối, không ghi đè.
  Tool này không lưu mẫu vào kho nhóm/team.

Quy tắc sử dụng cho agent dựng video (hành vi của phía gọi tool,
ghi tại đây để các job MCP về sau theo; không phải logic server):

- Trước khi áp, xem danh sách mẫu; ưu tiên mẫu của nhóm chủ đề của
  video rồi tới mẫu cá nhân; chỉ áp mẫu khớp dạng video và không
  vi phạm ràng buộc cảnh kết CTA ở Phần 1.
- Chỉ lưu mẫu mới khi kho chưa có mẫu phù hợp, và chỉ lưu từ video
  đã render xong, đạt kiểm tra QC khung hình — không lưu từ video
  lỗi hay bản nháp dở.
- Lượt dựng nào có chọn mẫu hoặc tạo mẫu mới đều phải ghi rõ
  trong báo cáo của lượt đó (video nào dùng mẫu nào, mẫu mới nào
  được tạo) để user duyệt lại và xoá nếu không ưng.

## Phần 6 — Drawer ngày ở tab Kế hoạch: bấm ra ngoài để đóng

Hiện trạng (user phản ánh + kiểm chứng sáng 09/11): ở tab Kế
hoạch 30 ngày của một nhóm chủ đề, panel/drawer chi tiết một
ngày (tiêu đề dạng "Ngày 3", có nút X và nút "+ Thêm ý") đang
mở thì **bấm ra ngoài không đóng được** — chỉ đóng bằng nút X.
Đối chiếu: brief Bổ sung 3 của đợt bán tự động (đã xong) chỉ yêu
cầu mở drawer khi bấm ngày ở chế độ Gọn và đóng drawer không
mất vị trí cuộn/bộ lọc — **không hề yêu cầu khoá đóng khi bấm
ra ngoài**; mặc định của Drawer trong Ant Design là bấm vùng
mờ (mask) sẽ đóng. Ảnh chụp lúc phản ánh cho thấy trang không
bị mờ khi panel mở — panel nhiều khả năng đang chạy không có
mask.

Việc cần làm:

- Xác định đúng thành phần đang dựng panel này **trong bản code
  đang chạy production** (Drawer của Ant Design hay panel tự
  dựng). Lưu ý: bản `PlanTab.tsx` trong working copy tại thời
  điểm viết brief chưa có drawer ngày này (ngày được chọn hiện
  thẻ ngay dưới lịch) — phải đối chiếu đúng nhánh/bản chứa
  drawer trước khi sửa, và nêu rõ trong báo cáo đã sửa ở đâu.
- Bật lại hành vi chuẩn: có lớp mờ (mask) và **bấm ra ngoài là
  đóng** (maskClosable), giữ nguyên nút X như hiện tại.
- Đóng drawer — bằng bấm ra ngoài hay nút X — **không mất vị
  trí cuộn của lịch, bộ lọc đang đặt và ngày đang chọn** (đúng
  yêu cầu cũ của Bổ sung 3); mở lại đúng ngày đó thì nội dung
  như trước lúc đóng.
- Nếu bên trong drawer đang có form sửa ý tưởng với nội dung
  chưa lưu, giữ nguyên mọi cơ chế bảo vệ hiện có nếu có; thay
  đổi hành vi đó (nếu cần) phải nêu trong báo cáo, không tự ý
  bỏ.
- Test web cho hành vi: mở drawer → bấm ra ngoài → drawer đóng;
  mở lại → trạng thái cuộn/lọc/ngày chọn còn nguyên.

## Ngoài phạm vi

- Không bỏ tầng nhóm chủ đề trong mẫu dựng — Phần 2 giữ tầng này.
  "Bỏ tầng nhóm" trong brief này chỉ là tầng **team** (công tắc
  chung và mặc định "của nhóm").
- Không gộp mẫu dựng vào bộ thiết lập mặc định và ngược lại: các
  thiết lập tách biệt, đổi cái này không đổi cái kia.
- Không đổi bản thân các mẫu: nội dung mẫu và cách lưu một mẫu từ
  video trên web giữ nguyên như hiện tại.
- Không làm luân phiên/xoay vòng mẫu tự động trong nhóm — nhóm
  dùng một mẫu mặc định cố định cho tới khi người dùng đổi; chọn
  mẫu khác cho từng video vẫn làm tay/qua MCP được theo chuỗi ưu
  tiên.
- Phần 4 chỉ siết quyền xoá; không làm lại phân quyền xem/sửa
  toàn hệ thống trong đợt này.
- Phần 5 không làm logic tự chọn mẫu ở phía server — server chỉ
  cung cấp tool, việc chọn/tạo mẫu là của agent gọi tool theo quy
  tắc đã ghi. Đợt này cũng chưa làm xoá/sửa mẫu qua MCP (và nếu
  sau này làm, vẫn theo quy tắc sở hữu ở Phần 4).
- Không đụng giọng theo nhóm chủ đề và các việc khác thuộc brief
  bán tự động đã xong.
- Không đụng job rs-mcp-morning-build: bước gác trong job vẫn giữ
  nguyên cho tới khi bản này lên production và được xác nhận; gỡ
  bước gác hay không là quyết định riêng của user sau đó.

## Nghiệm thu

Phần 1:

- User A đặt mẫu mặc định X, user B để trống: video mới của A ăn
  mẫu X (khi không có tầng cao hơn), video mới của B không áp
  mẫu; A đổi lựa chọn thì giá trị và giao diện của B không thay
  đổi.
- `GET /api/edit-templates` ở hai phiên đăng nhập khác nhau trả
  `default` khác nhau, đúng theo từng user.
- Video có cảnh kết CTA render ra không có lớp chữ cuối của mẫu
  chen sau CTA; cảnh CTA giữ nguyên nội dung.

Phần 2:

- Nhóm A gắn 2 mẫu, đặt mặc định X; nhóm B không gắn mẫu: video
  mới của nhóm A ăn mẫu X, video mới của nhóm B rơi xuống tầng
  tài khoản/không áp như Phần 1.
- Video thuộc nhóm A được chọn tay mẫu Y (mẫu còn lại của nhóm) →
  render ăn mẫu Y, không ăn X.
- Video tạo qua MCP trong nhóm A ăn mẫu mặc định của nhóm A.

Phần 3:

- User A sửa mặc định cá nhân → video mới của A khởi tạo theo bản
  mới; video mới của B không đổi.
- Không còn thao tác hay dữ liệu "mặc định của nhóm" nào làm thay
  đổi thiết lập khởi tạo của video mới (test: đổi/xoá dữ liệu mặc
  định nhóm cũ nếu còn → tạo video mới không khác gì).
- User chưa từng lưu mặc định cá nhân vẫn tạo được video, với bộ
  khởi tạo đã migrate như mục Migration.
- Trang Thiết lập mặc định chỉ còn phần của tài khoản (theo người
  dùng).

Phần 4:

- User B không xoá được video, nhóm chủ đề, mẫu cá nhân, sản phẩm
  affiliate và tư liệu của user A: giao diện không có thao tác
  xoá, gọi API trực tiếp bị từ chối 403.
- User A vẫn xoá được đồ của chính mình như trước.
- Xoá nhóm chủ đề còn chứa video do user khác tạo → bị chặn kèm
  lý do rõ ràng.
- Xoá qua MCP (ví dụ xoá cảnh) trên video của user khác bị từ
  chối tương tự.

Phần 5:

- Xem kho mẫu qua MCP trả đúng các mẫu thấy được trên web của
  cùng user (cá nhân + theo nhóm chủ đề).
- Áp mẫu X cho một video qua MCP → video đó phản ánh thành phần
  của mẫu X khi đọc lại/render; các video khác không bị ảnh hưởng.
- Lưu một video thành mẫu cá nhân qua MCP → mẫu xuất hiện trong
  danh sách qua MCP và trên trang Mẫu dựng ở mục cá nhân; lưu
  trùng tên bị từ chối, mẫu cũ giữ nguyên.
- Ba tool mới xuất hiện trong danh sách tool của MCP server sau
  deploy, đúng scope read/write như trên.

Phần 6:

- Drawer ngày đang mở, bấm ra ngoài (vùng mờ) → drawer đóng;
  bấm nút X vẫn đóng như trước.
- Đóng rồi mở lại đúng ngày đó: vị trí cuộn, bộ lọc và ngày
  đang chọn giữ nguyên.

Chung:

- Video tạo qua MCP ăn đúng mẫu theo chuỗi ưu tiên (chọn riêng
  trên video › mặc định của nhóm chủ đề › mặc định của tài khoản
  người tạo › không áp) và khởi tạo theo thiết lập mặc định cá
  nhân của tài khoản đó.
- Video cũ không thay đổi; áp mẫu thủ công vào một video trên web
  vẫn chạy như trước.
- Test api + web xanh; báo cáo 3 phần theo lệ team.
