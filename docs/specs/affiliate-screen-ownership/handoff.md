# Bàn giao: màn Affiliate theo chủ sở hữu (PR #176)

Nhánh `feature/affiliate-screen-ownership`, PR https://github.com/tuananh219ln/Reels-Studio/pull/176 (chưa merge).
Mọi thay đổi đã commit và đẩy lên; commit cuối `17c211c`. File này không commit nếu không cần.

## Đã xong trong PR

- API `/api/affiliate-products/videos`: `posts` (Page/tài khoản, chủ, `has_shopee_account`, trạng thái `comment`),
  `mine`, `manual_comment`, `thumbnail_url`, `knowledge_topic_id`; mỗi sản phẩm đã gắn có `commission` theo Page
  (`affiliate.commission_to`, dùng chung với `link_for`).
- "Đã dán link tay": migration `0071` (`videos.manual_comment`), `PUT /videos/{id}/manual`; worker bình luận bỏ qua,
  đổi sản phẩm không yêu cầu sửa bình luận, "Bình luận ngay" trả 409.
- Nhập file: `POST /import/preview`; `/import` không ghi đè sản phẩm người khác thêm (trả `kept`, `others`).
- `/options`: `topics[].mine` (theo Page sở hữu), `topics[].product_count`, `pages`. Sản phẩm: `created_by`,
  `has_saved_link`, `short_on_counts`, `video_count`.
- Web: tab Video đã đăng (Của tôi/Cả đội, lọc Page, 3 kiểu xem, chip Page theo nền tảng, cảnh báo hoa hồng, Dán
  tay); tab Sản phẩm (cột nhóm, Tôi thêm/Cả đội, tab trạng thái, nhập theo Page/nhóm có xem trước).
- Docs: `docs/ux-guidelines.md`, `docs/architecture.md`, `docs/decisions/2026-11-09-affiliate-screen-ownership.md`.

## Đang làm dở (chưa bắt đầu code): MCP chọn đúng sản phẩm của người dùng

Chủ app duyệt làm trong PR #176. Trong `api/src/reels_api/mcp_server.py`:

1. `list_affiliate_products` (khoảng dòng 525): mặc định chỉ trả sản phẩm người dùng đã thêm (`created_by_id ==
   me`), thêm tham số kiểu `whose: "mine" | "all"`; mỗi dòng thêm `created_by` và `mine`; thêm `video_id` tuỳ chọn để
   xếp sản phẩm cùng nhóm với video lên trước.
2. `set_video_products` (khoảng dòng 550): kết quả trả kèm, theo từng Page, hoa hồng về ai (lấy `commission` từ
   `_video_payload` của `routes_affiliate`), để trợ lý báo người dùng khi không phải về họ.
3. Câu hướng dẫn của server (khoảng dòng 155, đoạn "Video sản phẩm: …"): thêm "ưu tiên sản phẩm của chính người
   dùng; dùng sản phẩm của người khác thì báo hoa hồng về ai".
4. Test: sửa/thêm trong `api/tests/test_mcp.py` (test `test_affiliate_products_are_listed_and_only_approved_ones_attach`,
   khoảng dòng 975; helper `grant`, `call`, `payload`; `product` từ `test_affiliate_accounts`). Viết test hỏng trước.
5. Cập nhật `docs/chatgpt.md` (mô tả công cụ MCP) và thêm một gạch đầu dòng vào file quyết định.

## Còn lại sau đó

- Chạy toàn bộ pytest (lần chạy toàn bộ sau các thay đổi cuối chưa xong trên máy), E2E Affiliate, cập nhật mô tả PR.
- Ảnh chụp màn hình cho PR (người chụp).
- Migration `0071` có thể trùng số với PR của session "Quyền theo chủ sở hữu, đợt 2" (#177/#178): PR merge sau đổi số.
- Merge chỉ khi chủ app bảo, sau khi CI xanh (`gh pr merge 176 --merge`).
- Việc riêng đề xuất, chưa duyệt: mỗi thành viên lưu link riêng cho cùng một sản phẩm, bình luận dùng link của chủ Page
  (giải quyết hoa hồng đúng người khi chưa có App ID).

## Chạy test trên máy

- Postgres tạm: container `reels-affiliate-pg`, `127.0.0.1:55453`, database `reels_test` và `reels_e2e`
  (`docker start reels-affiliate-pg` nếu đã dừng).
- pytest: `cd api && TEST_DATABASE_URL="postgresql+psycopg://reels:reels@127.0.0.1:55453/reels_test" .venv/bin/python -m pytest -q`
- E2E: `cd web && E2E_DATABASE_URL="postgresql+psycopg://reels:reels@127.0.0.1:55453/reels_e2e" npx playwright test e2e/affiliate.spec.ts`
- Không chạy hai bộ test cùng lúc trên cùng database (bị deadlock).
