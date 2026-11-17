/*
 * Injected by background.js into the competitor's Reels tab (a window it opened in the member's own Chrome, signed in
 * to Facebook). Scrolls the grid like a person, one screen at a time with a 1.5–3 s random pause, reads each reel's id
 * and the view count the grid shows, and sends new ones to the background in batches. It stops after four scrolls
 * with nothing new, at the scan's limit, after 30 minutes, or at once on a checkpoint/login page: it never answers one.
 * The selectors come from selectors.json, so a Facebook change is fixed there.
 */
async function reelsStudioScanReels(scanId, maxVideos, selectors) {
  const IDLE_ROUNDS = 4;
  const BATCH = 50;
  const TIME_LIMIT_MS = 30 * 60 * 1000;
  const started = Date.now();
  const idPattern = new RegExp(selectors.reelId);
  const viewsPattern = new RegExp(selectors.views, "i");
  const seen = new Map(); // fb_video_id -> {fb_video_id, views_raw, position}
  let pending = [];

  const pause = (low, high) => new Promise((wait) => setTimeout(wait, low + Math.random() * (high - low)));
  // A closed background answers nothing: the scan carries on and the page notices the silence.
  const send = (message) => chrome.runtime.sendMessage({ ...message, scanId }).catch(() => {});
  const blocked = () => {
    if (selectors.checkpointUrl.some((part) => location.pathname.includes(part))) return true;
    const text = document.body ? document.body.innerText.slice(0, 5000) : "";
    return selectors.checkpointText.some((phrase) => text.includes(phrase));
  };
  const flush = async () => {
    while (pending.length) {
      await send({ type: "scan-batch", videos: pending.splice(0, BATCH) });
    }
  };
  const viewsOf = (link) => {
    // The count is a line of the card's own text ("4,5M", "288 N"); the first such line is it.
    const lines = (link.innerText || "").split("\n").map((line) => line.trim());
    return lines.find((line) => line && viewsPattern.test(line)) || null;
  };
  const read = () => {
    let added = 0;
    for (const link of document.querySelectorAll(selectors.reelLink)) {
      const id = (link.getAttribute("href") || "").match(idPattern)?.[1];
      if (!id) continue;
      const views = viewsOf(link);
      const known = seen.get(id);
      if (known) {
        if (!known.views_raw && views) {
          known.views_raw = views;
          pending.push(known);
        }
        continue;
      }
      if (seen.size >= maxVideos) break;
      const video = { fb_video_id: id, views_raw: views, position: seen.size };
      seen.set(id, video);
      pending.push(video);
      added += 1;
    }
    return added;
  };

  await pause(2500, 4000); // the page's first grid
  if (blocked()) {
    return { status: "partial", error: "Facebook đang yêu cầu xác minh hoặc đăng nhập: hãy xử lý tay rồi bấm Tiếp tục" };
  }
  let idle = 0;
  while (idle < IDLE_ROUNDS && seen.size < maxVideos) {
    idle = read() ? 0 : idle + 1;
    if (pending.length >= BATCH) await flush();
    send({ type: "scan-tick", found: seen.size });
    if (Date.now() - started > TIME_LIMIT_MS) {
      await flush();
      return { status: "partial", error: "Quá 30 phút, dừng để an toàn; bấm Tiếp tục để đọc tiếp", name: pageName() };
    }
    window.scrollBy(0, window.innerHeight * 0.9);
    await pause(1500, 3000);
    if (blocked()) {
      await flush();
      return { status: "partial", error: "Facebook hiện checkpoint/CAPTCHA: hãy xử lý tay rồi bấm Tiếp tục" };
    }
  }
  read();
  await flush();
  if (!seen.size) {
    return { status: "failed", error: "Không thấy Reels nào: trang không có Reels công khai, hoặc chưa đăng nhập Facebook" };
  }
  return { status: "done", name: pageName() };

  function pageName() {
    const heading = document.querySelector(selectors.pageName);
    return heading ? heading.innerText.trim().slice(0, 200) : null;
  }
}
