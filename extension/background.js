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
 * "Phân tích đối thủ": the Reels Studio page (/competitors) asks for a competitor's Reels grid to be read. One scan at
 * a time: a window opens on the grid in the member's own signed-in Chrome (a hidden tab would not load more videos as
 * it scrolls), facebook-reels.js scrolls and reads it, and every batch goes back to the page, which saves it. The
 * window is closed at the end, except on a checkpoint, which is left in front for the member to deal with.
 */
importScripts("facebook-reels.js");

let scanning = null; // {scanId, appTabId, windowId, tabId}

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
  toApp({ type: "scan-done", scanId, ...result });
  if (result.status !== "partial" || !String(result.error || "").includes("Facebook")) {
    chrome.windows.remove(windowId).catch(() => {});
  } else {
    chrome.windows.update(windowId, { focused: true }).catch(() => {});
  }
  scanning = null;
}

async function scanReels(message, appTabId) {
  const selectors = await (await fetch(chrome.runtime.getURL("selectors.json"))).json();
  const opened = await chrome.windows.create({ url: message.url, type: "normal", focused: true, width: 520, height: 900 });
  const tabId = opened.tabs[0].id;
  scanning = { scanId: message.scanId, appTabId, windowId: opened.id, tabId };
  await new Promise((loaded) => {
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
  });
  try {
    const [injected] = await chrome.scripting.executeScript({
      target: { tabId },
      func: reelsStudioScanReels,
      args: [message.scanId, message.maxVideos, selectors],
    });
    endScan(injected?.result || { status: "failed", error: "Không đọc được trang Facebook" });
  } catch {
    endScan({ status: "partial", error: "Cửa sổ Facebook đã đóng hoặc tải lại giữa chừng; bấm Tiếp tục để đọc tiếp" });
  }
}

chrome.windows.onRemoved.addListener((windowId) => {
  if (scanning && scanning.windowId === windowId) {
    endScan({ status: "partial", error: "Cửa sổ Facebook đã bị đóng; bấm Tiếp tục để đọc tiếp" });
  }
});

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type === "scan-reels" && sender.tab) {
    if (scanning) {
      reply({ started: false, error: "Tiện ích đang quét một đối thủ khác" });
      return false;
    }
    if (!/^https:\/\/www\.facebook\.com\//.test(String(message.url))) {
      reply({ started: false, error: "Link không phải Facebook" });
      return false;
    }
    scanReels(message, sender.tab.id);
    reply({ started: true });
    return false;
  }
  if ((message?.type === "scan-batch" || message?.type === "scan-tick") && scanning && sender.tab?.id === scanning.tabId) {
    toApp(message);
    reply({ ok: true });
    return false;
  }
  return false;
});
