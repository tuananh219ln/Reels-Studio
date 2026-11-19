# Brief: Trang chủ công khai cho TikTok duyệt app (app "Reels Studio" bị từ chối — mục App name)

## 0. Bàn giao

- Model: Sonnet, effort medium, KHÔNG dùng subagent. Đọc `AGENTS.md` và `web/AGENTS.md` trước khi sửa; agent chỉ commit/mở PR khi người dùng yêu cầu, không tự merge; không đụng production; test chỉ qua fake services, không gọi TikTok thật.
- Làm theo đúng thứ tự §5. Chạy lệnh kiểm tra liên quan sau mỗi bước; bước nào đỏ thì dừng và báo.
- Báo cáo 3 phần khi xong: Done / Verified (lệnh thật đã chạy, kết quả thật) / Remaining risks.
- Branch từ `main` (`feature/...`), PR nhỏ, mô tả PR tiếng Việt theo template, CI xanh mới được merge. Không commit vào `main`.

## 1. Vấn đề

- App developer TikTok "Reels Studio" (ID 7705106261222492167), nộp duyệt Production ngày 07/11/2026, bị từ chối. Chỉ 1 mục bị bắt: **App name**. Ghi chú của reviewer (nguyên văn, đã đọc trong portal ngày 19/11/2026): "The app name must be clearly displayed on the website and must match the website title, website URL and desktop URL. For example, if the app name is ABC123, the website should clearly identify itself as ABC123 and use the abc123.com domain consistently for the website, Privacy Policy and Terms of Service URLs."
- Giá trị đã đăng ký trong portal (đã đọc ngày 19/11/2026, không đổi trong PR này): App name "Reels Studio"; Web/Desktop URL https://reels.quangdang.xyz/; Terms of Service URL https://reels.quangdang.xyz/terms; Privacy Policy URL https://reels.quangdang.xyz/privacy; Description "Reels Studio is a web app that helps creators make short vertical videos (9:16) and publish them to TikTok."; demo video resize-tt.mp4 đã tải lên; Login Kit Redirect URI https://reels.quangdang.xyz/api/tiktok/oauth/callback; scopes user.info.basic / video.upload / video.publish; Direct Post bật.
- Trang web hiện tại (kiểm chứng live ngày 19/11/2026): trang chủ https://reels.quangdang.xyz/ chỉ là màn hình đăng nhập — tiêu đề "Reels Studio" + form đăng nhập ("Đăng nhập", "Công cụ nội bộ, không tự đăng ký tài khoản"). /terms và /privacy LÀ trang thật, mở được không cần đăng nhập (nội dung đầy đủ, cập nhật 06/11/2026). Tên và domain đã khớp (reels.quangdang.xyz dùng nhất quán cho cả 3 URL) — nhưng người lạ mở web không thấy mô tả sản phẩm nào, chỉ thấy form login. Thêm nữa, /terms và /privacy tự mô tả tool là "công cụ nội bộ của một nhóm nhỏ (khoảng 5 người)" chỉ đăng lên các Trang Facebook của nhóm — đọc như tool nội bộ đóng, mâu thuẫn với mô tả app "helps creators ... publish them to TikTok".
- Ảnh hưởng: Direct Post (đăng thẳng công khai) vẫn bị chặn; Sandbox không ảnh hưởng (@anlanhsk vẫn kết nối, đăng nháp vẫn được). Sửa xong web thì chủ tài khoản nộp lại trong portal (Return to Draft → resubmit) — bước nộp lại KHÔNG thuộc PR này, không tạo app mới, không bấm Recall, không đổi config trong portal.

## 2. Quyết định

1. Trang chủ `/` thành trang công khai (landing) — người lạ mở web thấy ngay tên + mô tả + link /terms, /privacy, và đường vào đăng nhập. Form đăng nhập giữ nguyên ở /login, không dời.
2. Nội dung landing viết tiếng Anh, bám sát mô tả app đã nộp trong portal (để reviewer đọc cùng một mô tả ở cả hai nơi). Form đăng nhập và phần còn lại của tool giữ tiếng Việt như hiện tại.
3. Không sửa nội dung /terms và /privacy trong PR này (đã là trang thật, đang mở được; nếu reviewer còn bắt thì đó là vòng sau, không phải PR này).

## 3. Sự thật đã kiểm chứng trên main (ngày 19/11/2026 — bám đúng, đừng tự chế)

- `web/src/app/page.tsx` (main): chỉ có `redirect("/videos")` — chưa có trang chủ công khai nào.
- `web/src/proxy.ts` (main): `SESSION_COOKIE = "reels_session"`; proxy redirect về /login khi không có cookie; matcher loại trừ đúng `/login`, `/privacy`, `/terms` (khớp chính xác), `/api/`, `_next/`, file có đuôi. Matcher hiện tại: `/((?!login|privacy$|terms$|api/|_next/|.*\\..*).*)`. Comment trong file ghi rõ: trang mới được chặn mặc định mà không cần sửa danh sách — nghĩa là muốn `/` công khai thì BẮT BUỘC phải sửa matcher này.
- `web/src/app/layout.tsx` (main): metadata `title: "Reels Studio"`, `description: "Công cụ nội bộ làm video dọc 9:16"`.
- `web/src/app/terms/page.tsx` và `web/src/app/privacy/page.tsx` (main): server component công khai, có Metadata riêng, kèm comment "Public, with no session: the proxy leaves /terms open (proxy.ts)" — đây là mẫu để làm theo cho trang chủ.
- `web/src/app/login/page.tsx` (main): client component, form đăng nhập trong `CenteredCard` ("Đăng nhập"), POST `/auth/login`, sau khi đăng nhập dùng `leaveSignIn`/`withNext` trong `@/lib/next` để quay lại trang đã yêu cầu trước đó.
- `web/e2e/app.spec.ts` (main, dòng 28–35): vòng lặp `for (const url of ["/", ...appPages, "/change-password"])` kiểm tra `${url} redirects to login on the server when there is no session`, kỳ vọng về `/login`. Dòng 37–60: /privacy và /terms mở được không cần session (status 200, đúng heading; /privacy-x và /terms-x vẫn redirect về login).
- Quy tắc repo (`AGENTS.md`): code/comment/docs/commit bằng tiếng Anh; nói với user tiếng Việt; mô tả PR tiếng Việt theo template; xong = lint + typecheck pass, có test cho hành vi đổi và test pass, docs trong `docs/` mô tả hành vi đổi được cập nhật cùng PR; branch từ main, PR nhỏ, CI xanh mới merge; không chạy lệnh trong terminal Coolify, không đụng database production; production chỉ đổi qua CI khi merge vào main.
- Next.js 16: đọc `web/AGENTS.md` và hướng dẫn trong `node_modules/next/dist/docs/` trước khi viết code web.

## 4. Thiết kế

### 4.1 Trang chủ công khai (`web/src/app/page.tsx`)

- Thay redirect vô điều kiện bằng landing page cho khách chưa đăng nhập; người đã đăng nhập (có session cookie) vẫn vào `/videos` như hiện tại.
- Cách nhận biết: đọc cookie `SESSION_COOKIE` (đã export từ `proxy.ts`) bằng `cookies()` của `next/headers` trong server component — có cookie thì `redirect("/videos")`, không có thì render landing. API vẫn tự kiểm tra session trên mọi request, nên đây chỉ là điều hướng, không phải kiểm tra quyền.
- Nội dung landing (tĩnh, không gọi API, không hiện dữ liệu người dùng):
  - H1 "Reels Studio" — tên hiện rõ ngay đầu trang.
  - Một đoạn mô tả tiếng Anh, bám sát mô tả app trong portal: "Reels Studio is a web app that helps creators make short vertical videos (9:16) and publish them to TikTok." (Giữ gần như nguyên văn để reviewer thấy cùng một mô tả ở cả hai nơi.)
  - Link tới /privacy và /terms (cùng domain, hiện rõ trên trang).
  - Nút/link "Đăng nhập" dẫn tới /login (đội vẫn vào tool bằng một cú bấm; không dời form đăng nhập).
  - Metadata riêng cho trang (theo mẫu /terms, /privacy): title "Reels Studio", description tiếng Anh như đoạn mô tả trên.
- Không thêm dependency mới. Giữ nguyên giao diện Ant Design và font hiện tại của tool.

### 4.2 Proxy (`web/src/proxy.ts`)

- Thêm trang chủ `/` vào nhóm công khai: sửa matcher để request GET `/` không có session trả về 200 với landing, không redirect.
- Gợi ý (KIỂM CHỨNG bằng test, đừng tin mù): phần còn lại sau `/` đầu tiên của `/` là chuỗi rỗng, nên thêm `$` vào nhóm loại trừ trong lookahead, ví dụ `(?!$|login|privacy$|terms$|api/|_next/|.*\\..*)` — kiểm chứng bằng E2E (§4.3) trước khi kết luận regex đúng.
- Cập nhật comment trong file để liệt kê `/` cùng /login, /privacy, /terms là các trang công khai.
- Không đổi hành vi còn lại: /videos và mọi trang trong `(app)` vẫn redirect về /login khi không có session; /privacy-x, /terms-x vẫn redirect.

### 4.3 Test (`web/e2e/app.spec.ts`)

- Bỏ `"/"` khỏi vòng lặp redirect-to-login (dòng 28) — trang chủ giờ công khai, không còn redirect.
- Thêm test mới theo đúng phong cách test /privacy hiện có (dòng 37–47): "the homepage opens without a session, for TikTok's app review" — GET `/` trả 200, H1 "Reels Studio" hiện, đoạn mô tả hiện, link tới /privacy và /terms bấm được và tới đúng trang.
- Thêm kiểm tra: người đã đăng nhập mở `/` vẫn tới `/videos` (giữ luồng vào tool của đội).

### 4.4 Bổ sung sau review (đã áp dụng)

- Hằng số cookie tách ra `web/src/lib/session.ts`; `proxy.ts` và `page.tsx` cùng import từ đó (không để page import `proxy.ts`). `cookies()` ở Next 16 là async (`await cookies()`).
- Landing thêm khối "How it works" (3 ý, khớp scope đã đăng ký) và bọc `lang="en"` vì layout là `lang="vi"`.
- Thêm file `docs/decisions/2026-11-19-public-homepage.md` và sửa đoạn "Three pages need no session" trong `docs/architecture.md`.
- Ghi nhận, ngoài phạm vi: matcher `login` không có `$` nên `/login-x` cũng công khai; /terms, /privacy vẫn nói "công cụ nội bộ ~5 người" và bằng tiếng Việt — rủi ro bị từ chối vòng sau.

### 4.5 Không làm trong PR này

- Không sửa nội dung /terms và /privacy.
- Không đổi gì trong portal TikTok (tên app, URL, mô tả, scope) và không nộp lại — chủ tài khoản tự nộp lại sau khi deploy.
- Không sửa trang /login và luồng đăng nhập; không thêm biến môi trường; không đổi API.

## 5. Các bước

1. Đọc `AGENTS.md`, `web/AGENTS.md`, `docs/decisions.md` (lướt tìm xung đột; nếu quyết định đã ghi mâu thuẫn với việc làm trang chủ công khai thì dừng và báo user).
2. Branch từ `main` (`feature/...`).
3. Sửa theo §4 theo đúng thứ tự: `proxy.ts` → `page.tsx` (+ metadata) → `app.spec.ts`.
4. Chạy `cd web && npm run format && npm run lint && npm run typecheck`, rồi `npm run e2e` (ít nhất file `app.spec.ts`); ghi kết quả thật.
5. Mở PR nhỏ, mô tả tiếng Việt theo template, báo cáo 3 phần: đổi gì / lệnh nào đã chạy và kết quả thật / còn dang dở hoặc phát hiện ngoài phạm vi.
6. Sau khi merge (CI deploy khi merge vào main), kiểm chứng live: khách chưa đăng nhập mở https://reels.quangdang.xyz/ thấy landing (tên + mô tả + link); /login vẫn đăng nhập được; /videos không session vẫn về /login. Sau đó chủ tài khoản nộp lại app trong portal TikTok (Return to Draft → resubmit).

## 6. Rủi ro

- Ghi chú của reviewer là mẫu chung; landing page là cách sửa có cơ sở nhất từ những gì đã kiểm chứng, nhưng duyệt hay không là quyết định của TikTok — brief này không bảo đảm đậu. Nếu bị từ chối tiếp, ghi chú lần sau sẽ nêu mục tiếp theo cần sửa.
- Đừng làm test xanh bằng cách nới lỏng nó: bỏ `"/"` khỏi vòng lặp redirect và thêm test trang chủ công khai thay vì xóa test.
- Không chạy lệnh trong terminal Coolify, không đụng database production (AGENTS.md).
