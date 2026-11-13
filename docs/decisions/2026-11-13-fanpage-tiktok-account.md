# Tài khoản TikTok gắn theo Page (2026-11-13)

## Quyết định

Mỗi Page chọn một tài khoản TikTok trên Quản lý Page; video của Page đó mở thẻ Đăng TikTok lên là tài khoản
đã chọn sẵn, không phải bấm chọn từng video nữa. Video nào không thuộc Page đã gắn thì vẫn chọn tay như cũ.

- DB: `fanpages.tiktok_account_id` (migration 0080, FK `affiliate_accounts.id` ON DELETE SET NULL). Cột này
  từng bị gỡ cùng lúc bỏ "Bán tự động" (0079); lựa chọn là của Page, không phải của một lượt chạy, nên nó quay
  lại một mình, không kèm `tiktok_own_version`, `prepare_time` hay `auto_prepare`.
- API: `PUT /fanpages/{id}/tiktok-account`, bám đúng mẫu `shopee-account`: chỉ chủ Page được gắn, tài khoản
  phải là TikTok của chính chủ và đang dùng; `null` là gỡ. `/fanpages` trả `tiktok_account` {id, name, connected}
  và chỉ chủ Page mới thấy. `video_payload` trả `tiktok_account_id` trong từng mục `fanpages` — chỉ là một id
  trần, người khác xem cũng không dùng được vì thẻ Đăng TikTok chỉ chọn sẵn id nào nằm trong danh sách tài khoản
  đã kết nối của chính người xem.
- Web: thẻ Page thêm ô chọn TikTok ngay dưới ô Shopee, chỉ chủ Page thấy; lựa chọn là tài khoản TikTok đang dùng
  của chính chủ, nhãn `TikTok: tên (@username)` khi đã kết nối; tài khoản đã chọn mà mất kết nối thì thẻ báo
  phải kết nối lại trong Cài đặt. Thẻ Đăng TikTok chọn sẵn tài khoản của Page đang đăng (Page đã chọn trong ngăn
  Đăng bài, nếu không thì Page của chính chủ thuộc nhóm của video, theo `myPageOfGroup`): ô "Đăng lên TikTok"
  chỉ nhận tài khoản còn kết nối, ô "Đã đăng tay" nhận mọi tài khoản TikTok của chủ. Việc chọn sẵn làm một lần
  cho mỗi video (và mỗi lần đổi Page), lựa chọn tay của thành viên không bao giờ bị ghi đè — tài khoản tải lại
  khi sản phẩm của video đổi thì không tính.
- Test: pytest trong `test_fanpages.py` (endpoint + payload video) và e2e trong `affiliate.spec.ts` (gắn trên
  thẻ Page) + `videos.spec.ts` (mở video đã chọn sẵn).

## Đã loại

- Tự chọn khi chỉ có đúng một tài khoản đã kết nối: không gắn theo Page, hỏng khi một người chạy nhiều Page với
  nhiều kênh TikTok khác nhau. Đề nghị này đã được thay bằng cách gắn theo Page.
- Lưu tài khoản vào video lúc dựng: video đã dựng rồi vẫn phải được hưởng lựa chọn của Page; lựa chọn của Page
  phải áp dụng ngược cho mọi video của Page đó.
- Tài khoản TikTok mặc định chung trong Cài đặt: tài khoản thuộc về Page, không thuộc về thành viên — một thành
  viên có thể sở hữu nhiều Page.
