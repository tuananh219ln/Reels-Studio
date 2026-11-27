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
  it opens an incognito window (brought back to the front whenever it is covered, since Facebook loads nothing in a hidden window), signs it in with that account's cookies (your own Facebook in normal windows is
  untouched), first reads the Page's header (name, followers, verified badge, and a 128 px copy of the avatar, and a small picture of each video it opens,
  which is why the extension may read `*.fbcdn.net`; "Cập nhật thông tin kênh" does only this), scrolls to the last reel card every 1.5–3 s (whichever box holds the grid: on a profile it is not the window), reads each reel's id and view count with `selectors.json` and sends
  them to the page in batches, then opens the most viewed reels one by one, 4–8 s apart, for caption, sound and
  reactions, and for the first of them up to 30 comments (text and likes, never who wrote them). With "Quét cả
  tab Video" it reads the Videos tab after Reels. A few videos spread down each grid are opened for their posting
  date only, so how often the competitor posts can be worked out. A checkpoint is left open for the member; it is never answered. The cookies stay in this Chrome and
  are never sent to Reels Studio's server. See `docs/decisions/2026-11-17-competitor-analyzer.md`.

- On "Affiliate › Sản phẩm" › "Nhập / Xuất", "Chuyển bằng tiện ích Chrome" (from 1.8.0, `shopee-convert`) turns the group's
  product pages into the member's own affiliate links with Shopee Affiliate's Custom Link: it finds or opens a
  `affiliate.shopee.vn` tab (the member must be signed in) and sends the requests from inside that tab, 20 links a request,
  1.5 s apart, with `Sub_id1` = the Page; Shopee signs the requests with its own page scripts. The links go back to the
  page, which previews them like a file. Reels Studio's server never calls Shopee. See
  `docs/decisions/2026-11-28-shopee-auto-link.md`. `manifest.json` gained `https://affiliate.shopee.vn/*`: Chrome asks
  the member to accept it when the extension is reloaded.

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

## Update (keeps the saved cookies)

`manifest.json` carries a fixed `key`, so the extension's id is always `ncnafhaoejkcbljpkomboinfnmkgolph` whatever
folder it is loaded from, and the second account's cookies (`chrome.storage.local`) survive every update.

1. Put the new files in place (`git pull`, or copy them over the old folder).
2. `chrome://extensions` › Reels Studio › the reload arrow (↻). Reload the Reels Studio tab.

Removing the extension and loading the new folder also works from 1.7.0: Chrome deletes the extension's own data,
but the "Đối thủ" page keeps a copy of the cookies in this Chrome (never on the server) and hands it back the next
time it is opened. Only "Cho phép ở chế độ ẩn danh" has to be turned on again. "Xóa" on the options page removes the
copy too (`docs/decisions/2026-11-18-scan-account-copy.md`).

The extension runs only on `https://reels.quangdang.xyz`, `http://localhost:3000`, Google's search pages and the
Facebook windows it opens for a scan. A new
version of the app domain needs `manifest.json` changed.
