/*
 * On Reels Studio's own pages: a bridge between the page (window.postMessage, source "reels-page") and the
 * extension's background script. The page never talks to Google; it asks the extension and gets addresses back.
 */
(() => {
  const VERSION = chrome.runtime.getManifest().version;
  const announce = () => window.postMessage({ source: "reels-extension", type: "ready", version: VERSION, features: ["shopee-convert"] }, "*");
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
    // "find": photos for some keywords; "target": the scene "Gửi ảnh vào Reels Studio" sends to; "scan-reels": read
    // a competitor's Reels grid.
    chrome.runtime.sendMessage(data, (answer) => {
      if (data.id) {
        window.postMessage({ source: "reels-extension", type: "answer", id: data.id, ...(answer || {}) }, "*");
      }
    });
  });
  // "Gửi ảnh vào Reels Studio" from another tab: the page puts the photo on the scene. A competitor scan's batches,
  // progress and end ("Phân tích đối thủ") go to the page that started it, which saves them.
  const TO_PAGE = new Set(["send-image", "scan-batch", "scan-tick", "scan-grid-done", "scan-detail", "scan-done"]);
  chrome.runtime.onMessage.addListener((message) => {
    if (TO_PAGE.has(message?.type)) {
      window.postMessage({ source: "reels-extension", ...message }, "*");
    }
  });
})();
