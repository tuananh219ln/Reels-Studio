/*
 * On Reels Studio's own pages: a bridge between the page (window.postMessage, source "reels-page") and the
 * extension's background script. The page never talks to Google; it asks the extension and gets addresses back.
 */
(() => {
  const VERSION = chrome.runtime.getManifest().version;
  const announce = () => window.postMessage({ source: "reels-extension", type: "ready", version: VERSION }, "*");
  announce();
  window.addEventListener("message", (event) => {
    const data = event.data;
    if (event.source !== window || !data || data.source !== "reels-page") {
      return;
    }
    if (data.type === "hello") {
      announce();
      return;
    }
    // "find": photos for some keywords; "target": the scene "Gửi ảnh vào Reels Studio" sends to.
    chrome.runtime.sendMessage(data, (answer) => {
      if (data.id) {
        window.postMessage({ source: "reels-extension", type: "answer", id: data.id, ...(answer || {}) }, "*");
      }
    });
  });
  // "Gửi ảnh vào Reels Studio" from another tab: the page puts the photo on the scene.
  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "send-image") {
      window.postMessage({ source: "reels-extension", ...message }, "*");
    }
  });
})();
