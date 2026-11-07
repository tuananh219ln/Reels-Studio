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
