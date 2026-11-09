# Brief: Màn Affiliate — lọc theo chủ sở hữu + minh bạch hoa hồng về ai

Nhánh: `feature/affiliate-screen-ownership` (tách từ `main`)

## Bối cảnh

Mô hình tiền của tool (đã chốt 2026-11-02): **tool dùng chung, tiền nhận riêng** — mỗi thành viên có Fanpage, tài khoản TikTok và tài khoản Shopee affiliate RIÊNG; tiền hoa hồng của một lượt đăng thuộc về chủ của nơi đăng lượt đó.

Link trong bình luận lúc đăng (`affiliate.comment_text` → `link_for`):

- Page có tài khoản Shopee **dùng được** (`affiliate.page_account()`: tài khoản gắn với page, vẫn thuộc chủ page, đang dùng, có App ID + Secret) → sinh link riêng bằng tài khoản đó.
- Không có → dùng **link lưu sẵn** `AffiliateProduct.url`, là link của người đã thêm sản phẩm (`created_by_id`).
- Không có tài khoản dùng được VÀ sản phẩm không có `url` (chỉ có `page_url`, ví dụ thêm bằng link trang sản phẩm) → sản phẩm **bị bỏ khỏi bình luận, không báo gì**.

Sản phẩm gắn theo **video**, nên mọi lượt đăng còn sống của video (có thể trên nhiều Page) đều mang các sản phẩm đó.

Các quyết định 2026-11-08 đã đưa Video, Bài viết, Bài đăng, Bình luận, Jobs về "Của tôi / Cả đội" nhưng để Affiliate ngoài phạm vi. Brief này đưa nốt màn Affiliate về cùng quy tắc, **không đặt quy tắc mới**:

- "Every list of the team's work starts on the member's own, 'Cả đội' one click away" (2026-11-08): bài đăng là của tôi khi **tôi đăng nó hoặc nó nằm trên Page tôi sở hữu**; danh sách mở ở "Của tôi" khi đã có dòng của mình, nếu không mở ở "Cả đội".
- "A member's own Pages and topic groups come first where one is picked" (2026-11-08): **nhóm của tôi = nhóm chủ đề của các Page tôi sở hữu và đang dùng** (`fanpages.owner_id` + `fanpages.knowledge_topic_id`). KHÔNG dùng `KnowledgeTopic.created_by_id` (cột này chỉ để xét quyền xoá, điền đoán, có thể null).

## Hiện trạng đã kiểm chứng (code trên `main`, 2026-11-09)

- `GET /api/affiliate-products/videos` (`list_videos`): mọi video có lượt đăng Facebook/TikTok đã lên, không lọc người; mỗi video một dòng theo lượt đăng mới nhất; payload không có Page hay chủ.
- Lượt đăng TikTok **không có `fanpage_id`**; chủ của nó là chủ tài khoản affiliate `Publication.affiliate_account_id`.
- `_payload` sản phẩm có `created_by_id`, `problems`, `checked_by`; chưa có tên người thêm.
- Tab Sản phẩm **đã** hiện `problems` dưới trạng thái và **đã** có `QuickFill` sửa nhanh sao / lượt bán / loại shop — nhưng chỉ khi sản phẩm Shopee, Nháp, loại shop "other", `rating == 0` và `sold == 0` (`needsQuickFill`).
- Bộ lọc nhóm tab Sản phẩm **đã** lấy `options.topics` từ `/options` (đủ mọi nhóm, không số đếm). Lỗi "chỉ thấy 2 nhóm, có số trong ngoặc, thiếu 'Ăn Lành Sống Khỏe'" quan sát trên UI **chưa tái hiện được từ code** (danh sách có "(N video)" là bộ lọc *sản phẩm* bên tab Video).
- Drawer "Thêm sản phẩm" **đã** có cảnh báo khi `shopee_lookup = false`.
- Mọi dữ kiện cần ĐÃ CÓ: `Publication.fanpage_id`, `Publication.affiliate_account_id`, `Publication.created_by_id`, `Fanpage.owner_id`, `Fanpage.shopee_account_id`, `Fanpage.knowledge_topic_id`, `AffiliateAccount.owner_id`, `AffiliateProduct.created_by_id`. **Không migration, không đổi mô hình dữ liệu.**

## Nguyên tắc xuyên suốt

1. "Của tôi / Cả đội" theo đúng quy tắc 2026-11-08 (định nghĩa, nhãn, cách chọn mặc định).
2. Gắn sản phẩm chéo vẫn ĐƯỢC phép — không chặn, chỉ báo **ai nhận hoa hồng** ngay tại chỗ chọn, mỗi Page một dòng.
3. Tiền về ai được tính ở **một chỗ phía API**, cùng logic với lúc đăng (`page_account()` / `link_for`); giao diện chỉ hiển thị, không tự suy.
4. Không đụng: luật duyệt (4.7 sao / 100 lượt bán, giữ nguyên), worker bình luận + subId, cơ chế sinh link, MCP, tab Doanh thu, quyền xoá (delete-by-maker).

## Phần 1 — Tab "Video đã đăng": Của tôi / Cả đội + Page của từng lượt đăng

API (`routes_affiliate.py`, `list_videos` / `_video_payload`):

- Mỗi video bổ sung `posts`: danh sách **mọi lượt đăng còn sống** (`is_published`) của video, mỗi phần tử:
  `{platform, fanpage_id, fanpage_name, owner_id, owner_name, has_shopee_account}`
  - Facebook: Page = `Publication.fanpage_id`; chủ = `Fanpage.owner_id`; `has_shopee_account` = `affiliate.page_account(db, page) is not None` (KHÔNG phải `shopee_account_id is not None`).
  - TikTok: không có Page; chủ = `AffiliateAccount.owner_id` của `Publication.affiliate_account_id`; `fanpage_*` = null; tên hiển thị là tên tài khoản TikTok/affiliate.
  - Các trường cũ (`platform`, `reel_url`, `published_at` theo lượt đăng mới nhất) giữ nguyên.
- Thêm `mine: bool` cho mỗi video: true khi **có ít nhất một** lượt đăng còn sống mà tôi đăng (`Publication.created_by_id`) hoặc tôi là chủ (chủ Page với Facebook, chủ tài khoản affiliate với TikTok).
- Không thêm query param: danh sách đã tải đủ một lần (như các danh sách nạp đủ khác), giao diện lọc theo `mine`. Nạp sẵn Page / tài khoản / tên người một lần, không truy vấn theo từng video.

Giao diện (tab "Video đã đăng"):

- Segmented "Của tôi | Cả đội"; mở ở "Của tôi" nếu có video `mine`, nếu không mở ở "Cả đội". Các chip đếm (Tất cả / Chưa gắn / Đã gắn / Cần xem lại) đếm trong phạm vi đang chọn.
- Mỗi dòng hiện thêm (chữ nhỏ dưới tiêu đề) Page/tài khoản của từng lượt đăng kèm tên chủ.

## Phần 2 — Ai nhận hoa hồng: một quy tắc, một dòng mỗi Page

API: thêm hàm thuần trong `affiliate.py`, ví dụ `commission_to(page_account, product) -> {kind, user_name}` với `kind`:

- `page_account` — Page có tài khoản dùng được → tiền về chủ tài khoản đó (chủ Page).
- `saved_link` — không có tài khoản dùng được, sản phẩm có `url` → tiền về người thêm sản phẩm.
- `no_link` — không có tài khoản dùng được, sản phẩm không có `url` → sản phẩm sẽ **không xuất hiện** trong bình luận.

Hàm dùng chung điều kiện với `link_for` (test khẳng định hai bên khớp). `_payload` bổ sung `created_by` (tên, theo mẫu `checked_by`) và `has_saved_link` (`url is not None`); sản phẩm lồng trong `_video_payload` cũng có `created_by_id`, `created_by`, `has_saved_link`.

Giao diện (ô chọn sản phẩm của một video, tab Video đã đăng): với mỗi lượt đăng Facebook mà kết quả **không phải** "tiền về chính tôi", hiện đúng một dòng cảnh báo (không chặn):

- `page_account`, chủ Page là người khác: "Page <tên page>: hoa hồng về tài khoản Shopee của <chủ page>."
- `saved_link`, người thêm khác chủ Page: "Page <tên page> chưa có tài khoản Shopee dùng được — bình luận dùng link của <người thêm>, hoa hồng về tài khoản đó."
- `no_link`: "Page <tên page> chưa có tài khoản Shopee dùng được và sản phẩm chưa có link affiliate — sản phẩm sẽ không có trong bình luận."

Lượt đăng TikTok không áp dụng (sản phẩm TikTok Shop theo tài khoản TikTok của người đăng).

Tab "Sản phẩm": mỗi dòng hiện "Người thêm: <tên>" (chữ nhỏ dưới tên shop), tooltip: "Link lưu sẵn của sản phẩm được dùng trong bình luận khi Page đăng bài chưa có tài khoản Shopee dùng được." (Ghi "Người thêm", không ghi "Link của", vì `url` có thể đã được người khác sửa.)

## Phần 3 — Bộ lọc nhóm chủ đề (tab Sản phẩm)

- `GET /api/affiliate-products/options`: mỗi `topic` bổ sung `mine: bool` = nhóm là `knowledge_topic_id` của một Page tôi sở hữu và đang dùng (cùng định nghĩa quyết định 2026-11-08; dùng lại hàm sẵn có nếu đã có).
- Bộ lọc chia hai cụm "Nhóm của tôi" / "Nhóm khác", nhóm của tôi lên trước; không có số đếm.
- Lỗi "thiếu nhóm, số đếm lạ": **tái hiện trước** (test hoặc kiểm trên bản chạy từ `main`). Tái hiện được → test hỏng trước, rồi sửa. Không tái hiện được trên `main` → ghi trong PR là lỗi của bản cũ, không sửa gì thêm.

## Phần 4 — Sửa nhanh sao / lượt bán (thu gọn)

- Lý do chưa duyệt và `QuickFill` đã có; chỉ mở rộng `needsQuickFill` để hiện cho **mọi sản phẩm Nháp có lý do về sao hoặc lượt bán** (không đòi đồng thời `rating == 0`, `sold == 0`, loại shop "other"), giữ điều kiện `lookup !== "pending"`. Không sửa API duyệt.
- Không làm banner App ID riêng: cảnh báo trong drawer "Thêm sản phẩm" đã có, giữ nguyên.

## Ngoài phạm vi

- Không thêm trường chủ sở hữu vào sản phẩm; kho sản phẩm vẫn dùng chung theo nhóm chủ đề.
- Không chặn gắn chéo; không đổi luật duyệt; không đụng worker bình luận, subId, MCP, tab Doanh thu, quyền xoá.
- Khi thêm link trùng sản phẩm đã có, link của người sau bị bỏ (giữ sản phẩm cũ) — biết, không sửa ở đây.

## Kiểm thử

API (pytest, theo mẫu test affiliate hiện có, 2 thành viên / 2 Page / 1 kết nối TikTok):

- `mine` đúng cho: video trên Page tôi; video tôi đăng trên Page người khác; video của người khác trên Page người khác (false); video đăng ở Page tôi rồi được đăng lại trên Page người khác (vẫn true); video TikTok qua tài khoản affiliate của tôi.
- `posts` liệt kê đủ lượt đăng còn sống, đúng tên Page/chủ; `has_shopee_account` false khi Page gắn tài khoản thiếu App ID hoặc tài khoản không còn thuộc chủ Page.
- `commission_to` đủ 3 trường hợp và khớp với `link_for` (cùng dữ kiện: `no_link` ⇔ `link_for` trả None).
- `_payload` có `created_by`, `has_saved_link`; `/options` có `topic.mine` đúng theo Page sở hữu.

E2E (`web/e2e/affiliate.spec.ts`, chạy local trước khi push): mặc định "Của tôi" và chuyển "Cả đội"; dòng video hiện Page + chủ; cảnh báo hoa hồng khi gắn sản phẩm người khác thêm vào video trên Page chưa có tài khoản dùng được; bộ lọc nhóm có cụm "Nhóm của tôi"; QuickFill hiện cho sản phẩm Nháp thiếu sao/lượt bán.

## Docs và quyết định

- Cập nhật phần affiliate trong `docs/architecture.md` (payload `posts`, `mine`, `commission_to`) và `docs/ux-guidelines.md` (Của tôi / Cả đội, dòng cảnh báo hoa hồng) nếu có mô tả màn này.
- Ghi file MỚI `docs/decisions/2026-11-09-affiliate-screen-ownership.md`: màn Affiliate theo "Của tôi / Cả đội" của quyết định 2026-11-08 (thay câu "Affiliate (out of the brief's scope) are not filtered" của quyết định đó); nhóm của tôi theo Page sở hữu; video TikTok thuộc chủ tài khoản affiliate; giao diện báo hoa hồng về ai theo cùng logic sinh link lúc đăng, kể cả trường hợp sản phẩm không có link.

## Quy tắc làm việc

- Đọc `AGENTS.md` và `docs/decisions/` trước khi làm. Không dùng subagent. TDD, test bằng service giả như các test affiliate hiện có.
- Nhận việc trước: mở draft PR ngay khi tạo nhánh; không merge khi chưa được duyệt.
- Báo cáo 3 phần trong PR (tiếng Việt, theo template): đã làm / đã kiểm (lệnh và kết quả thật) / còn lại và rủi ro.
