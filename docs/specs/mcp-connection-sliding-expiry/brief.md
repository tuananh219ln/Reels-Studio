# Brief Reels Studio — Kết nối MCP: đổi hạn cứng 30 ngày thành hạn trượt 30 ngày

> **Việc MỚI, brief riêng** — user chốt sáng 09/11/2026.
>
> Thi công theo lệ team: đọc AGENTS.md + docs/decisions.md và
> các file quyết định riêng trong docs/decisions/ trước; làm
> trên **nhánh mới** `feat/mcp-connection-sliding-expiry` tạo từ
> main; TDD, test bằng fake services, báo cáo 3 phần, không tự
> merge. Quyết định phát sinh ghi thành **file riêng trong
> docs/decisions/** theo quy ước mới, không append vào
> docs/decisions.md.

## Bối cảnh và hiện trạng (kiểm chứng trong code, 09/11)

- `api/src/reels_api/mcp_auth.py`: `ACCESS_LIFETIME = timedelta(hours=1)`,
  `CONNECTION_LIFETIME = timedelta(days=30)`.
- Endpoint token trong `api/src/reels_api/routes_mcp.py`: grant
  `authorization_code` tạo `McpConnection` với
  `expires_at = now() + CONNECTION_LIFETIME`; grant
  `refresh_token` kiểm tra `connection.expires_at > now()` rồi
  gọi `rotate_tokens(connection)` — rotate chỉ cấp access token
  mới với hạn `min(now() + 1 giờ, connection.expires_at)`,
  **không hề gia hạn `connection.expires_at`**.
- Hệ quả: mọi kết nối MCP (Muse, Claude, ChatGPT, Claude Code)
  **chết hẳn sau đúng 30 ngày kể từ lúc thành viên bấm đồng ý**,
  dù được dùng mỗi ngày; muốn dùng tiếp phải duyệt kết nối lại
  từ đầu. Kết nối Muse hiện tại (duyệt 08/11) hết hạn khoảng
  08/12 — trong khi job dựng video mỗi sáng của user chạy qua
  chính kết nối này.
- Kết nối còn buộc vào phiên đăng nhập của thành viên
  (`member_session`): phiên hết hạn/bị thu hồi thì kết nối chết
  theo. Đây là tính chất bảo mật **cố ý, giữ nguyên**.

## Thay đổi yêu cầu

1. **Gia hạn khi refresh thành công:** trong nhánh
   `refresh_token` của endpoint token, sau khi các kiểm tra hợp
   lệ hiện tại đã qua và trước khi `rotate_tokens`, đặt
   `connection.expires_at = now() + CONNECTION_LIFETIME`.
   (Nếu người thi công thấy đặt trong `rotate_tokens` sạch hơn
   thì chấp nhận được, với điều kiện đường `authorization_code`
   không đổi hành vi; chọn cách nào phải nêu trong báo cáo.)
2. **Chỉ gia hạn khi còn hạn:** kết nối đã hết hạn thì refresh
   vẫn bị từ chối đúng như hiện tại — hạn trượt không hồi sinh
   kết nối đã chết.
3. **Kết nối hiện hữu được hưởng ngay:** mọi `McpConnection`
   đã cấp trước thay đổi này tự áp dụng hạn trượt từ lần
   refresh đầu tiên sau khi deploy — không migration dữ liệu,
   không bắt thành viên duyệt lại.

## Giữ nguyên tuyệt đối

- Access token 1 giờ, cơ chế xoay token (rotate cả access +
  refresh), scope `reels:read` / `reels:write`, allowlist
  callback, endpoint revoke.
- Ràng buộc phiên thành viên: đăng xuất mọi nơi, đổi mật khẩu,
  khoá tài khoản vẫn giết kết nối ngay như hiện tại.
- **Không** làm token vô hạn tuyệt đối — user đã cân nhắc và
  chọn hạn trượt: đang dùng thì sống, bỏ không dùng đủ 30 ngày
  thì tự hết hạn.

## Ngoài phạm vi

- Không đổi thời hạn phiên đăng nhập web.
- Không làm cảnh báo "kết nối sắp hết hạn" trong đợt này.
- Không đụng `mcp_server.py` và các tool MCP — khu vực đó đang
  có nhánh `feat/per-user-settings-ownership` thi công; brief
  này chỉ đụng `mcp_auth.py`, `routes_mcp.py` và test tương
  ứng.

## Test (TDD, bổ sung vào `api/tests/test_mcp.py`)

- Refresh một kết nối sắp hết hạn (ví dụ còn 1 ngày) →
  `expires_at` được đẩy thành khoảng now + 30 ngày, và access
  token mới được cấp bình thường theo hạn mới.
- Refresh một kết nối **đã** hết hạn → vẫn bị từ chối như hiện
  tại.
- Một kết nối "cũ" (tạo mô phỏng theo cách trước thay đổi)
  refresh lần đầu sau thay đổi → được gia hạn.
- Toàn bộ `test_mcp.py` và test api xanh; test web không liên
  quan (không đổi giao diện).

## Nghiệm thu

- Kết nối được dùng liên tục (refresh đều) không bao giờ chạm
  mốc chết 30 ngày; kết nối bỏ không dùng quá 30 ngày thì hết
  hạn và refresh bị từ chối.
- Thu hồi kết nối / đăng xuất / khoá tài khoản vẫn giết kết
  nối ngay như trước.
- Quyết định được ghi thành file riêng
  `docs/decisions/2026-11-09-mcp-connection-sliding-expiry.md`:
  đổi hạn cứng → hạn trượt, lý do vận hành (job tự động phụ
  thuộc vào kết nối), và phần giữ nguyên (ràng buộc phiên,
  mốc 30 ngày không dùng).
- Báo cáo 3 phần theo lệ team.
