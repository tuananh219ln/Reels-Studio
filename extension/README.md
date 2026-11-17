# Reels Studio – Google Ảnh và Đối thủ (Chrome extension)

Takes photos from Google Ảnh for Reels Studio's scenes inside a member's own Chrome; the server never searches
Google (see `docs/decisions.md`, 2026-11-08).

- On a video's page, "Lấy ảnh Google cho cảnh thiếu ảnh" asks the extension to open Google Ảnh in a background tab
  for each scene's keywords, read the photos' addresses from the results and close the tab. The page attaches the
  first photo the api accepts (stock photo sites are refused). One search at a time, 1.5 s apart; a CAPTCHA page
  stops it and is brought to the front for the member to solve.
- On any site, an image's right-click menu has "Gửi ảnh vào Reels Studio: <scene>", which sends it to the scene whose
  "Tìm trên Google" was pressed last.

- On "Phân tích đối thủ" (`/competitors`), while the page is open, the extension reads a competitor's Facebook Reels
  grid for each scan the page claims, always as the second Facebook account saved on the extension's options page:
  it opens an incognito window, signs it in with that account's cookies (your own Facebook in normal windows is
  untouched), scrolls a screen every 1.5–3 s, reads each reel's id and view count with `selectors.json` and sends
  them to the page in batches, then opens the most viewed reels one by one, 4–8 s apart, for caption, sound and
  reactions, and for the first of them up to 30 comments (text and likes, never who wrote them). With "Quét cả
  tab Video" it reads the Videos tab after Reels. A few videos spread down each grid are opened for their posting
  date only, so how often the competitor posts can be worked out. A checkpoint is left open for the member; it is never answered. The cookies stay in this Chrome and
  are never sent to Reels Studio's server. See `docs/decisions/2026-11-17-competitor-analyzer.md`.

## Second Facebook account (for "Phân tích đối thủ")

1. `chrome://extensions` › this extension › "Chi tiết" › turn on "Cho phép ở chế độ ẩn danh".
2. In an incognito window, sign in to Facebook as the second account and copy facebook.com's cookies
   (Cookie-Editor › Export › JSON, or the `cookie` request header from DevTools). `c_user` and `xs` are required.
3. The extension's options ("Tùy chọn", or "Cài đặt tài khoản phụ" on the Đối thủ page) › paste › "Lưu".
   Close that incognito window without logging out: logging out ends the cookies.

## Install (each member, once)

1. Chrome › `chrome://extensions` › turn on "Developer mode".
2. "Load unpacked" › pick this `extension/` folder.
3. Reload the Reels Studio tab. The video page shows "Lấy ảnh Google cho cảnh thiếu ảnh" once it sees the extension.

The extension runs only on `https://reels.quangdang.xyz`, `http://localhost:3000`, Google's search pages and the
Facebook windows it opens for a scan. A new
version of the app domain needs `manifest.json` changed.
