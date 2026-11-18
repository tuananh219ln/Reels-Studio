/*
 * The extension's background: opens Google Ảnh in background tabs for "Lấy ảnh Google cho cảnh thiếu ảnh", and adds
 * "Gửi ảnh vào Reels Studio" to every image's right-click menu. Searches go one at a time with a pause between them,
 * like a person would; a CAPTCHA page stops everything and is left open for the member to solve.
 */
const PAUSE_MS = 1500;
const TAB_TIMEOUT_MS = 20000;
const MENU_ID = "reels-send-image";
const waiting = new Map(); // request id -> resolve

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: MENU_ID, title: "Gửi ảnh vào Reels Studio", contexts: ["image"] });
});

function searchUrl(keyword, request) {
  return `https://www.google.com/search?q=${encodeURIComponent(keyword)}&udm=2&hl=vi#reels-${request}`;
}

function photosFor(keyword) {
  const request = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return new Promise((resolve) => {
    chrome.tabs.create({ url: searchUrl(keyword, request), active: false }, (tab) => {
      // Google's "unusual traffic" page lives at /sorry/: stop there and show it to the member.
      const watch = (tabId, change) => {
        if (tabId === tab.id && change.url && change.url.includes("/sorry/")) {
          chrome.tabs.update(tab.id, { active: true });
          done({ photos: [], captcha: true });
        }
      };
      const done = (answer) => {
        if (!waiting.has(request)) {
          return;
        }
        waiting.delete(request);
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(watch);
        if (!answer.captcha) {
          chrome.tabs.remove(tab.id).catch(() => {});
        }
        resolve(answer);
      };
      const timer = setTimeout(() => done({ photos: [], error: "timeout" }), TAB_TIMEOUT_MS);
      waiting.set(request, done);
      chrome.tabs.onUpdated.addListener(watch);
    });
  });
}

async function find(keywords) {
  const results = [];
  for (const [index, keyword] of keywords.entries()) {
    if (index > 0) {
      await new Promise((wait) => setTimeout(wait, PAUSE_MS));
    }
    const answer = await photosFor(keyword);
    results.push({ keyword, photos: answer.photos || [], error: answer.error });
    if (answer.captcha) {
      return { results, captcha: true };
    }
  }
  return { results };
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type === "google-results") {
    waiting.get(message.request)?.({ photos: message.photos });
    return false;
  }
  if (message?.type === "find" && Array.isArray(message.keywords)) {
    find(message.keywords.slice(0, 20)).then(reply);
    return true; // the answer comes later
  }
  if (message?.type === "target" && sender.tab) {
    chrome.storage.session.set({ target: { ...message.target, tabId: sender.tab.id } });
    chrome.contextMenus.update(MENU_ID, { title: `Gửi ảnh vào Reels Studio: ${message.target.label}` });
    reply({ ok: true });
    return false;
  }
  return false;
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== MENU_ID || !info.srcUrl) {
    return;
  }
  const { target } = await chrome.storage.session.get("target");
  if (!target) {
    return;
  }
  chrome.tabs.sendMessage(target.tabId, { type: "send-image", sceneId: target.sceneId, url: info.srcUrl });
});

/*
 * "Phân tích đối thủ": the Reels Studio page (/competitors) asks for a competitor's Reels to be read. One scan at a
 * time, always as the member's second Facebook account (scan-account.js), in an incognito window so their own
 * Facebook is never touched; a window, not a hidden tab, because a hidden tab does not load more videos as it
 * scrolls. 1) facebook-reels.js reads the grid and every batch goes back to the page, which saves it; 2) the page
 * answers with the most viewed reels ("scan-details"), whose own pages are opened one by one, 4–8 s apart, for caption,
 * sound and reactions. The window is closed at the end, except on a checkpoint, left in front for the member.
 */
importScripts("scan-account.js", "facebook-reels.js");

const REEL_PAUSE_MS = [4000, 8000];
let scanning = null; // {scanId, appTabId, windowId, tabId, selectors}

function toApp(message) {
  if (scanning) {
    chrome.tabs.sendMessage(scanning.appTabId, message).catch(() => {});
  }
}

function endScan(result) {
  if (!scanning) {
    return;
  }
  const { scanId, windowId } = scanning;
  const { keepOpen, ...ended } = result;
  // What the Page's header gave (name, followers, badge, avatar) goes with the end, whatever the end was.
  const meta = scanning.meta || {};
  // The header's name first: it is read with more care than the grid's (Messenger's heading is left out there).
  toApp({ type: "scan-done", scanId, ...meta, ...ended, name: meta.name || ended.name || null });
  if (keepOpen) {
    chrome.windows.update(windowId, { focused: true }).catch(() => {});
  } else {
    chrome.windows.remove(windowId).catch(() => {});
  }
  scanning = null;
}

function loadIn(tabId, url) {
  return new Promise((loaded) => {
    // "complete" may come before this listens: the timer reads the page anyway.
    const timer = setTimeout(() => done(), TAB_TIMEOUT_MS);
    const listen = (id, change) => {
      if (id === tabId && change.status === "complete") {
        done();
      }
    };
    const done = () => {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listen);
      loaded();
    };
    chrome.tabs.onUpdated.addListener(listen);
    chrome.tabs.update(tabId, { url });
  });
}

async function run(func, args) {
  const [injected] = await chrome.scripting.executeScript({ target: { tabId: scanning.tabId }, func, args });
  return injected?.result;
}

/** Why a scan cannot start in this Chrome, or null. */
async function cannotScan(account) {
  if (!account) {
    return "Chưa lưu cookie tài khoản Facebook phụ trong tiện ích (Tùy chọn của tiện ích)";
  }
  if (!(await chrome.extension.isAllowedIncognitoAccess())) {
    return "Hãy bật \"Cho phép ở chế độ ẩn danh\" cho tiện ích Reels Studio trong chrome://extensions";
  }
  return null;
}

async function scanReels(message, appTabId, account) {
  const selectors = await (await fetch(chrome.runtime.getURL("selectors.json"))).json();
  const opened = await chrome.windows.create({
    url: "about:blank",
    incognito: true,
    type: "normal",
    focused: true,
    width: 520,
    height: 900,
  });
  const tabId = opened.tabs[0].id;
  scanning = { scanId: message.scanId, appTabId, windowId: opened.id, tabId, selectors };
  try {
    await signInScanTab(tabId, account);
    await loadIn(tabId, message.url);
    const meta = await run(reelsStudioReadMeta, [selectors]);
    if (meta?.stopped) {
      endScan(
        meta.stopped === "login"
          ? { status: "partial", error: "Tài khoản phụ không còn đăng nhập (cookie hết hạn hoặc bị đăng xuất): lấy cookie mới, lưu trong tiện ích rồi bấm Tiếp tục" }
          : { status: "partial", keepOpen: true, error: "Facebook hiện checkpoint/CAPTCHA với tài khoản phụ: hãy xử lý tay trong cửa sổ đó rồi bấm Tiếp tục" },
      );
      return;
    }
    if (meta) {
      const { avatar_src: source, ...read } = meta;
      scanning.meta = { ...read, avatar: await imageCopy(source) };
    }
    if (message.metaOnly) {
      endScan({ status: "done" });
      return;
    }
    let grid = await run(reelsStudioScanReels, [message.scanId, message.maxVideos, selectors, "reel"]);
    const reelsEmpty = grid?.empty;
    // M5: the Videos tab after Reels, when the scan asks for it; a page without Reels may still have videos.
    if (message.videosUrl && grid && (grid.status === "done" || reelsEmpty)) {
      const name = grid.name;
      await loadIn(tabId, message.videosUrl);
      grid = await run(reelsStudioScanReels, [message.scanId, message.maxVideos, selectors, "video"]);
      if (grid?.empty && !reelsEmpty) {
        grid = { status: "done", name };
      } else if (grid && !grid.name) {
        grid.name = name;
      }
    }
    if (!grid || grid.status !== "done") {
      endScan(grid || { status: "failed", error: "Không đọc được trang Facebook" });
      return;
    }
    // The page saves the last batch, then sends the videos to open ("scan-details") or closes the scan.
    toApp({ type: "scan-grid-done", scanId: message.scanId, name: grid.name });
  } catch (error) {
    endScan({
      status: "partial",
      error: scanning && error?.message?.includes("cookie")
        ? error.message
        : "Cửa sổ Facebook đã đóng hoặc tải lại giữa chừng; bấm Tiếp tục để đọc tiếp",
    });
  }
}

/**
 * A picture (the avatar, a video's) as a small JPEG data URL (128 px), or null: fetched here because the background
 * may read Facebook's image servers while a page may not (CORS), and shrunk so what goes to Reels Studio stays a few
 * KB.
 */
async function imageCopy(source) {
  if (!source) return null;
  try {
    const host = new URL(source).hostname;
    if (!(host.endsWith(".fbcdn.net") || host.endsWith(".facebook.com"))) return null;
    const response = await fetch(source);
    if (!response.ok) return null;
    const bitmap = await createImageBitmap(await response.blob());
    const scale = Math.min(1, 128 / Math.max(bitmap.width, bitmap.height));
    const canvas = new OffscreenCanvas(Math.max(1, Math.round(bitmap.width * scale)), Math.max(1, Math.round(bitmap.height * scale)));
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await canvas.convertToBlob({ type: "image/jpeg", quality: 0.85 });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return `data:image/jpeg;base64,${btoa(binary)}`;
  } catch {
    return null;
  }
}

/** Opens each target's own page, 4–8 s apart: {id, url, comments}, the url always one of Facebook's own. */
async function readReels(targets) {
  const scanId = scanning.scanId;
  for (const [index, { id, url, comments }] of targets.entries()) {
    if (!scanning || scanning.scanId !== scanId) {
      return;
    }
    if (index > 0) {
      const [low, high] = REEL_PAUSE_MS;
      await new Promise((wait) => setTimeout(wait, low + Math.random() * (high - low)));
    }
    try {
      await loadIn(scanning.tabId, url);
      const detail = await run(reelsStudioReadReel, [scanning.selectors, comments]);
      if (detail?.stopped === "checkpoint") {
        endScan({
          status: "partial",
          keepOpen: true,
          error: "Facebook hiện checkpoint/CAPTCHA khi mở từng video: hãy xử lý tay rồi bấm Tiếp tục",
        });
        return;
      }
      if (detail?.stopped === "login") {
        endScan({ status: "partial", error: "Tài khoản phụ bị đăng xuất khi mở từng video: lấy cookie mới rồi bấm Tiếp tục" });
        return;
      }
      const { thumb_src: pictureSource, ...read } = detail;
      toApp({
        type: "scan-detail",
        scanId,
        video: { fb_video_id: id, ...read, thumbnail: await imageCopy(pictureSource) },
      });
      toApp({ type: "scan-tick", scanId, read: index + 1, of: targets.length });
    } catch {
      endScan({ status: "partial", error: "Cửa sổ Facebook đã đóng khi đang mở từng video; bấm Tiếp tục để đọc tiếp" });
      return;
    }
  }
  endScan({ status: "done" });
}

chrome.windows.onRemoved.addListener((windowId) => {
  if (scanning && scanning.windowId === windowId) {
    endScan({ status: "partial", error: "Cửa sổ Facebook đã bị đóng; bấm Tiếp tục để đọc tiếp" });
  }
});

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type === "scan-account" && sender.tab) {
    scanAccountStatus().then(reply);
    return true;
  }
  if (message?.type === "open-options") {
    chrome.runtime.openOptionsPage();
    reply({ ok: true });
    return false;
  }
  if (message?.type === "scan-reels" && sender.tab) {
    if (scanning) {
      reply({ started: false, error: "Tiện ích đang quét một đối thủ khác" });
      return false;
    }
    const facebook = (url) => /^https:\/\/www\.facebook\.com\//.test(String(url));
    if (!facebook(message.url) || (message.videosUrl && !facebook(message.videosUrl))) {
      reply({ started: false, error: "Link không phải Facebook" });
      return false;
    }
    scanAccount().then(async (account) => {
      const refused = await cannotScan(account);
      if (refused) {
        reply({ started: false, error: refused });
        return;
      }
      scanReels(message, sender.tab.id, account);
      reply({ started: true });
    });
    return true;
  }
  if (message?.type === "scan-details" && scanning && message.scanId === scanning.scanId) {
    // From the api through the page: each with its own address (a reel, or a video of the Videos tab). An older
    // page sends only ids and comment ids: each is opened as a reel.
    const commentIds = new Set(Array.isArray(message.commentIds) ? message.commentIds.map(String) : []);
    const given = Array.isArray(message.targets)
      ? message.targets.map((target) => ({ id: String(target.fb_video_id), url: String(target.url), comments: Boolean(target.comments) }))
      : (Array.isArray(message.ids) ? message.ids : []).map((id) => ({
          id: String(id),
          url: `https://www.facebook.com/reel/${id}/`,
          comments: commentIds.has(String(id)),
        }));
    const targets = given
      .filter((target) => /^\d{5,30}$/.test(target.id) && target.url.startsWith("https://www.facebook.com/"))
      .slice(0, 150);
    if (targets.length) {
      readReels(targets);
    } else {
      endScan({ status: "done" });
    }
    reply({ ok: true });
    return false;
  }
  if ((message?.type === "scan-batch" || message?.type === "scan-tick") && scanning && sender.tab?.id === scanning.tabId) {
    toApp(message);
    reply({ ok: true });
    return false;
  }
  return false;
});
