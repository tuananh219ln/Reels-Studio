/*
 * Injected by background.js into the scan's incognito window (signed in as the member's second Facebook account,
 * scan-account.js). Each function is run on its own by chrome.scripting, so it uses nothing outside itself. The
 * selectors come from selectors.json: a Facebook change is fixed there, following links and text, never Facebook's
 * generated class names. Neither answers a checkpoint or a login page: they stop and say so.
 */

/**
 * The competitor's Reels grid: scrolls like a person, one screen at a time with a 1.5–3 s random pause, reads each
 * reel's id and the view count the grid shows, and sends new ones in batches. It stops after four scrolls with
 * nothing new, at the scan's limit, after 30 minutes, or at once on a checkpoint or login page.
 */
async function reelsStudioScanReels(scanId, maxVideos, selectors) {
  const IDLE_ROUNDS = 4;
  const BATCH = 50;
  const TIME_LIMIT_MS = 30 * 60 * 1000;
  const started = Date.now();
  const idPattern = new RegExp(selectors.reelId);
  const viewsPattern = new RegExp(selectors.views, "i");
  const seen = new Map(); // fb_video_id -> {fb_video_id, views_raw, position}
  const pending = [];

  const pause = (low, high) => new Promise((wait) => setTimeout(wait, low + Math.random() * (high - low)));
  // A closed background answers nothing: the scan carries on and the page notices the silence.
  const send = (message) => chrome.runtime.sendMessage({ ...message, scanId }).catch(() => {});
  const stopped = () => {
    const text = document.body ? document.body.innerText.slice(0, 5000) : "";
    if (selectors.loginUrl.some((part) => location.pathname.includes(part)) || document.querySelector(selectors.loginForm)) {
      return {
        status: "partial",
        error: "Tài khoản phụ không còn đăng nhập (cookie hết hạn hoặc bị đăng xuất): lấy cookie mới, lưu trong tiện ích rồi bấm Tiếp tục",
      };
    }
    if (
      selectors.checkpointUrl.some((part) => location.pathname.includes(part)) ||
      selectors.checkpointText.some((phrase) => text.includes(phrase))
    ) {
      return {
        status: "partial",
        keepOpen: true,
        error: "Facebook hiện checkpoint/CAPTCHA với tài khoản phụ: hãy xử lý tay trong cửa sổ đó rồi bấm Tiếp tục",
      };
    }
    return null;
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
  const pageName = () => {
    const heading = document.querySelector(selectors.pageName);
    return heading ? heading.innerText.trim().slice(0, 200) : null;
  };

  await pause(2500, 4000); // the page's first grid
  const first = stopped();
  if (first) return first;
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
    const halt = stopped();
    if (halt) {
      await flush();
      return halt;
    }
  }
  read();
  await flush();
  if (!seen.size) {
    return { status: "failed", error: "Không thấy Reels nào: trang không có Reels công khai, hoặc tài khoản phụ không xem được" };
  }
  return { status: "done", name: pageName() };
}

/**
 * One reel's own page (/reel/<id>/): its caption (after pressing "Xem thêm"), sound, length and the reaction, comment
 * and share counts as written ("1,2K"), and with `withComments` a sample of its comments. Returns {stopped} on a
 * checkpoint or login page instead.
 */
async function reelsStudioReadReel(selectors, withComments) {
  const pause = (low, high) => new Promise((wait) => setTimeout(wait, low + Math.random() * (high - low)));
  const text = (element) => (element ? (element.innerText || element.textContent || "").trim() : "");
  await pause(2000, 3500);
  const body = document.body ? document.body.innerText.slice(0, 5000) : "";
  if (selectors.loginUrl.some((part) => location.pathname.includes(part)) || document.querySelector(selectors.loginForm)) {
    return { stopped: "login" };
  }
  if (
    selectors.checkpointUrl.some((part) => location.pathname.includes(part)) ||
    selectors.checkpointText.some((phrase) => body.includes(phrase))
  ) {
    return { stopped: "checkpoint" };
  }
  // Comments are articles; the caption is the reel's own text, outside them.
  const outsideComments = (element) => !element.closest(selectors.comment);
  for (const button of document.querySelectorAll(selectors.button)) {
    if (selectors.seeMore.includes(text(button)) && outsideComments(button)) {
      button.click();
      await pause(400, 900);
      break;
    }
  }
  let caption = "";
  for (const candidate of document.querySelectorAll(selectors.captionCandidates)) {
    const value = text(candidate);
    if (value.length >= selectors.captionMinLength && outsideComments(candidate) && !candidate.querySelector(selectors.captionCandidates)) {
      caption = value;
      break;
    }
  }
  if (!caption) {
    caption = document.querySelector('meta[property="og:description"]')?.getAttribute("content") || "";
  }
  const audio = text(document.querySelector(selectors.audioLink));
  const video = document.querySelector("video");
  const duration = video && Number.isFinite(video.duration) ? Math.round(video.duration) : null;
  const counts = {};
  const labels = [...document.querySelectorAll("[aria-label]")]
    .filter(outsideComments)
    .map((element) => element.getAttribute("aria-label"));
  for (const [field, patterns] of Object.entries(selectors.counts)) {
    for (const pattern of patterns) {
      const expression = new RegExp(pattern, "i");
      const found = labels.map((label) => label.match(expression)).find(Boolean);
      if (found) {
        counts[field] = found[1];
        break;
      }
    }
  }
  return {
    caption: caption.replace(/\s*(Ẩn bớt|See less)$/i, "").slice(0, 20000),
    audio_name: audio.slice(0, 1000) || null,
    duration_s: duration,
    reactions_raw: counts.reactions || null,
    comments_raw: counts.comments || null,
    shares_raw: counts.shares || null,
    comment_samples: withComments ? await commentSamples() : [],
  };

  /**
   * Up to 30 of the first comments shown under the reel (M4): opens the comments, scrolls their list a few times like
   * a reader, and keeps each comment's text and its likes as written. Who wrote it is never read.
   */
  async function commentSamples() {
    const opener = [...document.querySelectorAll(selectors.button)].find(
      (element) => outsideComments(element) && selectors.commentOpeners.includes(element.getAttribute("aria-label")),
    );
    if (opener) {
      opener.click();
      await pause(1500, 2500);
    }
    const samples = new Map(); // text -> likes as written
    for (let round = 0; round < selectors.commentScrolls && samples.size < selectors.commentsPerVideo; round += 1) {
      const articles = [...document.querySelectorAll(selectors.comment)];
      for (const article of articles) {
        // The body is the comment's own text block; the author's name is a link, outside it.
        const body = [...article.querySelectorAll(selectors.commentText)].find(
          (element) => !element.closest("a") && text(element).length > 1,
        );
        const value = text(body).slice(0, 2000);
        if (!value || samples.has(value)) continue;
        let likes = null;
        for (const pattern of selectors.counts.reactions) {
          const expression = new RegExp(pattern, "i");
          const found = [...article.querySelectorAll("[aria-label]")]
            .map((element) => element.getAttribute("aria-label").match(expression))
            .find(Boolean);
          if (found) {
            likes = found[1];
            break;
          }
        }
        samples.set(value, likes);
        if (samples.size >= selectors.commentsPerVideo) break;
      }
      const last = articles[articles.length - 1];
      if (!last) break;
      last.scrollIntoView({ block: "end" });
      await pause(1200, 2200);
    }
    return [...samples].map(([value, likes]) => ({ text: value, likes_raw: likes }));
  }
}
