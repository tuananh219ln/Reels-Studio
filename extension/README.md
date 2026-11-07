# Reels Studio – Google Ảnh (Chrome extension)

Takes photos from Google Ảnh for Reels Studio's scenes inside a member's own Chrome; the server never searches
Google (see `docs/decisions.md`, 2026-11-08).

- On a video's page, "Lấy ảnh Google cho cảnh thiếu ảnh" asks the extension to open Google Ảnh in a background tab
  for each scene's keywords, read the photos' addresses from the results and close the tab. The page attaches the
  first photo the api accepts (stock photo sites are refused). One search at a time, 1.5 s apart; a CAPTCHA page
  stops it and is brought to the front for the member to solve.
- On any site, an image's right-click menu has "Gửi ảnh vào Reels Studio: <scene>", which sends it to the scene whose
  "Tìm trên Google" was pressed last.

## Install (each member, once)

1. Chrome › `chrome://extensions` › turn on "Developer mode".
2. "Load unpacked" › pick this `extension/` folder.
3. Reload the Reels Studio tab. The video page shows "Lấy ảnh Google cho cảnh thiếu ảnh" once it sees the extension.

The extension runs only on `https://reels.quangdang.xyz`, `http://localhost:3000` and Google's search pages. A new
version of the app domain needs `manifest.json` changed.
