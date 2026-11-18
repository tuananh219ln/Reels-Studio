/*
 * Injected by background.js into the scan's incognito window (signed in as the member's second Facebook account,
 * scan-account.js). Each function is run on its own by chrome.scripting, so it uses nothing outside itself. The
 * selectors come from selectors.json: a Facebook change is fixed there, following links and text, never Facebook's
 * generated class names. Neither answers a checkpoint or a login page: they stop and say so.
 */

/**
 * The competitor's Reels grid, or with `kind` "video" its Videos tab: scrolls like a person, one screen at a time with
 * a 1.5–3 s random pause, reads each video's id and the view count the grid shows, and sends new ones in batches
 * (each with its grid's `type`, places counted on each grid apart). It stops after four scrolls with nothing new, at
 * the scan's limit, after 30 minutes, or at once on a checkpoint or login page.
 */
async function reelsStudioScanReels(scanId, maxVideos, selectors, kind = "reel") {
  const IDLE_ROUNDS = 6;
  const BATCH = 50;
  const TIME_LIMIT_MS = 30 * 60 * 1000;
  const started = Date.now();
  const linkSelector = kind === "video" ? selectors.videoLink : selectors.reelLink;
  const idPattern = new RegExp(kind === "video" ? selectors.videoId : selectors.reelId);
  const viewsPattern = new RegExp(selectors.views, "i");
  const seen = new Map(); // fb_video_id -> {fb_video_id, views_raw, position}
  const pending = [];

  /*
   * Messenger's panel ("Đoạn chat", "Các đoạn chat của bạn chưa được sao lưu"), opened by Facebook after a new sign-in:
   * its close button is pressed and the panel is hidden, and nothing inside it is ever read (it gave every reel the
   * caption "Các đoạn chat…", the scan time as posting date, a channel the name "Đoạn chat", and blocked the grid's
   * scroll). The panel is the highest block around one of its markers that does not hold the page's own content.
   * Defined in each injected function: Chrome runs each alone.
   */
  const hideMessenger = () => {
    const content = document.querySelector('[role="main"]') || document.querySelector("video");
    if (!content) return 0;
    let found = 0;
    for (const element of document.querySelectorAll("h1, h2, h3, span")) {
      if (content.contains(element) || element.closest("[data-reels-hidden]")) continue;
      if (!selectors.messengerMarkers.includes((element.textContent || "").trim())) continue;
      let panel = element;
      while (panel.parentElement && panel.parentElement !== document.body && !panel.parentElement.contains(content)) {
        panel = panel.parentElement;
      }
      if (panel.contains(content)) continue;
      for (const button of panel.querySelectorAll('[role="button"], button')) {
        const label = (button.getAttribute("aria-label") || button.textContent || "").trim();
        if (selectors.messengerClose.includes(label)) {
          button.click();
          break;
        }
      }
      panel.setAttribute("data-reels-hidden", "messenger");
      panel.style.display = "none";
      found += 1;
    }
    return found;
  };
  const facebookOwn = '[data-reels-hidden], [role="banner"], [role="navigation"], [role="complementary"]';
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
    for (const link of document.querySelectorAll(linkSelector)) {
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
      const video = { fb_video_id: id, views_raw: views, position: seen.size, type: kind };
      seen.set(id, video);
      pending.push(video);
      added += 1;
    }
    return added;
  };
  const pageName = () => {
    // The Page's real name: the main area's heading when it is one (never Messenger's "Đoạn chat" panel or Facebook's
    // bars), else the tab title ("(2) Linh Đoàn - Reels | Facebook").
    const headings = (root) =>
      [...root.querySelectorAll(selectors.pageName)].filter((h) => !h.closest(facebookOwn) && !h.closest('[role="dialog"]'));
    const main = document.querySelector('[role="main"]');
    const heading = (main && headings(main)[0]) || null;
    const generic = /^(facebook|reels|video|videos|thông báo|notifications|đoạn chat|chats|tin nhắn|messages)$/i;
    const headingText = heading ? heading.innerText.trim() : "";
    if (headingText && !generic.test(headingText)) return headingText.slice(0, 200);
    const meta = document.querySelector('meta[property="og:title"]');
    const raw = (meta && meta.content) || document.title || "";
    const title = raw
      .replace(/^\(\d+\+?\)\s*/, "")
      .replace(/\s*[|\-–—]\s*Facebook\s*$/i, "")
      .replace(/\s*[|\-–—]\s*(Reels|Video|Videos)\s*$/i, "")
      .trim();
    return title && !generic.test(title) ? title.slice(0, 200) : null;
  };

  await pause(2500, 4000); // the page's first grid
  const first = stopped();
  if (first) return first;
  let idle = 0;
  let rounds = 0;
  let messenger = 0;
  while (idle < IDLE_ROUNDS && seen.size < maxVideos) {
    messenger += hideMessenger();
    rounds += 1;
    idle = read() ? 0 : idle + 1;
    if (pending.length >= BATCH) await flush();
    send({ type: "scan-tick", found: seen.size });
    if (Date.now() - started > TIME_LIMIT_MS) {
      await flush();
      return { status: "partial", error: "Quá 30 phút, dừng để an toàn; bấm Tiếp tục để đọc tiếp", name: pageName() };
    }
    // The last card is brought into view, so whichever box holds the grid scrolls: on a profile (profile.php?id=…)
    // the grid is not in the window's own scroll, and scrolling the window alone stopped every profile at 10 reels.
    const cards = document.querySelectorAll(linkSelector);
    if (cards.length) {
      // A round with nothing new moves the last card to the top edge and back to the bottom one, so a loader that
      // watches for it to come into view sees it come in again.
      cards[cards.length - 1].scrollIntoView({ block: idle ? "start" : "end" });
      if (idle) {
        await pause(400, 800);
        cards[cards.length - 1].scrollIntoView({ block: "end" });
      }
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
    const what = kind === "video" ? "video nào ở tab Video" : "Reels nào";
    return {
      status: "failed",
      empty: true,
      error: `Không thấy ${what}: trang không có ${kind === "video" ? "video" : "Reels"} công khai, hoặc tài khoản phụ không xem được`,
    };
  }
  // Stopped before the limit: why, kept with the scan (the tooltip on its status), so a short grid can be told apart
  // from one that would not load more.
  const why = messenger ? `đã ẩn khung Messenger ${messenger} lần` : "không thấy khung Messenger";
  const note =
    seen.size < maxVideos
      ? `Dừng ở ${seen.size} video: lưới không tải thêm sau ${IDLE_ROUNDS} lần cuộn (${rounds} vòng, ${why}, trang cao ${document.documentElement.scrollHeight}px)`
      : null;
  return { status: "done", name: pageName(), error: note };
}

/**
 * One reel's own page (/reel/<id>/): its caption (after pressing "Xem thêm"), sound, length and the reaction, comment
 * and share counts as written ("1,2K"), and with `withComments` a sample of its comments. Returns {stopped} on a
 * checkpoint or login page instead.
 */
async function reelsStudioReadReel(selectors, withComments) {
  /*
   * Messenger's panel ("Đoạn chat", "Các đoạn chat của bạn chưa được sao lưu"), opened by Facebook after a new sign-in:
   * its close button is pressed and the panel is hidden, and nothing inside it is ever read (it gave every reel the
   * caption "Các đoạn chat…", the scan time as posting date, a channel the name "Đoạn chat", and blocked the grid's
   * scroll). The panel is the highest block around one of its markers that does not hold the page's own content.
   * Defined in each injected function: Chrome runs each alone.
   */
  const hideMessenger = () => {
    const content = document.querySelector('[role="main"]') || document.querySelector("video");
    if (!content) return 0;
    let found = 0;
    for (const element of document.querySelectorAll("h1, h2, h3, span")) {
      if (content.contains(element) || element.closest("[data-reels-hidden]")) continue;
      if (!selectors.messengerMarkers.includes((element.textContent || "").trim())) continue;
      let panel = element;
      while (panel.parentElement && panel.parentElement !== document.body && !panel.parentElement.contains(content)) {
        panel = panel.parentElement;
      }
      if (panel.contains(content)) continue;
      for (const button of panel.querySelectorAll('[role="button"], button')) {
        const label = (button.getAttribute("aria-label") || button.textContent || "").trim();
        if (selectors.messengerClose.includes(label)) {
          button.click();
          break;
        }
      }
      panel.setAttribute("data-reels-hidden", "messenger");
      panel.style.display = "none";
      found += 1;
    }
    return found;
  };
  const facebookOwn = '[data-reels-hidden], [role="banner"], [role="navigation"], [role="complementary"]';
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
  hideMessenger();
  // Comments are articles; the caption is the reel's own text, outside them and outside Facebook's own parts.
  const outsideComments = (element) => !element.closest(selectors.comment) && !element.closest(facebookOwn);
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
    if (
      value.length >= selectors.captionMinLength &&
      outsideComments(candidate) &&
      !selectors.messengerMarkers.includes(value) &&
      !candidate.querySelector(selectors.captionCandidates)
    ) {
      caption = value;
      break;
    }
  }
  if (!caption) {
    caption = document.querySelector('meta[property="og:description"]')?.getAttribute("content") || "";
  }
  const audio = text(document.querySelector(selectors.audioLink));
  // The posting time as written ("3 ngày", "17 tháng 10"): the first short text of the video's own part that looks
  // like one; the api reads the date from it.
  // Case matters: "5M" is a view count, "5m" five minutes.
  const postedPattern = new RegExp(selectors.posted);
  let posted = "";
  for (const candidate of document.querySelectorAll(selectors.postedCandidates)) {
    const value = text(candidate);
    if (value.length <= 40 && outsideComments(candidate) && postedPattern.test(value)) {
      posted = value;
      break;
    }
  }
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
  // The video's picture, for a small copy the background makes (like the avatar).
  const picture = document.querySelector('meta[property="og:image"]')?.getAttribute("content") || "";
  return {
    thumb_src: /^https:\/\//.test(picture) ? picture : null,
    caption: caption.replace(/\s*(Ẩn bớt|See less)$/i, "").slice(0, 20000),
    audio_name: audio.slice(0, 1000) || null,
    posted_raw: posted.slice(0, 200) || null,
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

/**
 * The Page's header, read before its grid: the real name (the heading when it is one, else the tab title), the
 * followers as written ("125 N"), whether a verified badge sits beside the name, and the avatar's address (the
 * background fetches and shrinks it: Facebook's own link is signed and expires). Whatever is not found is null.
 * Returns {stopped} on a login or checkpoint page, like the grid.
 *
 * Chrome injects this function alone (chrome.scripting.executeScript `func`): everything it uses is defined inside it,
 * never beside it in this file.
 */
async function reelsStudioReadMeta(selectors) {
  /*
   * Messenger's panel ("Đoạn chat", "Các đoạn chat của bạn chưa được sao lưu"), opened by Facebook after a new sign-in:
   * its close button is pressed and the panel is hidden, and nothing inside it is ever read (it gave every reel the
   * caption "Các đoạn chat…", the scan time as posting date, a channel the name "Đoạn chat", and blocked the grid's
   * scroll). The panel is the highest block around one of its markers that does not hold the page's own content.
   * Defined in each injected function: Chrome runs each alone.
   */
  const hideMessenger = () => {
    const content = document.querySelector('[role="main"]') || document.querySelector("video");
    if (!content) return 0;
    let found = 0;
    for (const element of document.querySelectorAll("h1, h2, h3, span")) {
      if (content.contains(element) || element.closest("[data-reels-hidden]")) continue;
      if (!selectors.messengerMarkers.includes((element.textContent || "").trim())) continue;
      let panel = element;
      while (panel.parentElement && panel.parentElement !== document.body && !panel.parentElement.contains(content)) {
        panel = panel.parentElement;
      }
      if (panel.contains(content)) continue;
      for (const button of panel.querySelectorAll('[role="button"], button')) {
        const label = (button.getAttribute("aria-label") || button.textContent || "").trim();
        if (selectors.messengerClose.includes(label)) {
          button.click();
          break;
        }
      }
      panel.setAttribute("data-reels-hidden", "messenger");
      panel.style.display = "none";
      found += 1;
    }
    return found;
  };
  const facebookOwn = '[data-reels-hidden], [role="banner"], [role="navigation"], [role="complementary"]';
  hideMessenger();
  // Facebook's own parts around the Page: the top bar (the scan account's picture), the side columns, Messenger.
  const ours = (element) => !element.closest(facebookOwn) && !element.closest('[role="dialog"]');
  /**
   * The Page's own avatar, never the signed-in account's: the first square picture of at least 40 px in the smallest
   * block around the name that holds one, then in the main area (a commenter's or a reaction's tiny picture, or the
   * cover beside the name, is not it). Null when none is found.
   */
  const pageAvatar = (heading) => {
    const big = (image) => {
      const box = (image.closest("svg") || image).getBoundingClientRect();
      return box.width >= 40 && box.height >= 40 && Math.abs(box.width - box.height) <= 0.2 * Math.max(box.width, box.height);
    };
    const usable = (root) => [...root.querySelectorAll(selectors.avatarImage)].filter((image) => ours(image) && big(image));
    let block = heading && heading.parentElement;
    for (let depth = 0; block && depth < 10; depth += 1, block = block.parentElement) {
      if (block.matches('[role="main"], body')) break;
      const found = usable(block);
      if (found.length) return found[0];
    }
    const main = document.querySelector('[role="main"]');
    return (main && usable(main)[0]) || null;
  };
  await new Promise((wait) => setTimeout(wait, 2500 + Math.random() * 1500));
  const body = document.body ? document.body.innerText.slice(0, 8000) : "";
  if (selectors.loginUrl.some((part) => location.pathname.includes(part)) || document.querySelector(selectors.loginForm)) {
    return { stopped: "login" };
  }
  if (
    selectors.checkpointUrl.some((part) => location.pathname.includes(part)) ||
    selectors.checkpointText.some((phrase) => body.includes(phrase))
  ) {
    return { stopped: "checkpoint" };
  }
  const generic = /^(facebook|reels|video|videos|thông báo|notifications|đoạn chat|chats|tin nhắn|messages)$/i;
  // The name is the first heading of the Page itself: inside the main area when there is one, never Facebook's own.
  const headings = (root) => [...root.querySelectorAll(selectors.pageName)].filter(ours);
  const main = document.querySelector('[role="main"]');
  // Only the main area's heading: outside it the first h1 may be Messenger's (the tab title is used instead).
  const heading = (main && headings(main)[0]) || null;
  let name = heading ? heading.innerText.trim() : "";
  if (!name || generic.test(name)) {
    const meta = document.querySelector('meta[property="og:title"]');
    const raw = (meta && meta.content) || document.title || "";
    name = raw
      .replace(/^\(\d+\+?\)\s*/, "")
      .replace(/\s*[|\-–—]\s*Facebook\s*$/i, "")
      .replace(/\s*[|\-–—]\s*(Reels|Video|Videos)\s*$/i, "")
      .trim();
  }
  if (generic.test(name)) name = "";
  const followers = body.match(new RegExp(selectors.followers, "i"));
  const header = heading && heading.parentElement && heading.parentElement.parentElement;
  const verified = Boolean(header && header.querySelector(selectors.verified));
  let avatar = document.querySelector('meta[property="og:image"]')?.getAttribute("content") || "";
  if (!avatar) {
    try {
      const image = pageAvatar(heading);
      avatar = (image && (image.getAttribute("xlink:href") || image.getAttribute("href") || image.getAttribute("src"))) || "";
    } catch {
      // The name and followers are still sent without a picture.
      avatar = "";
    }
  }
  return {
    name: name ? name.slice(0, 200) : null,
    followers: followers ? followers[1].trim() : null,
    is_verified: verified,
    avatar_src: /^https:\/\//.test(avatar) ? avatar : null,
  };
}
