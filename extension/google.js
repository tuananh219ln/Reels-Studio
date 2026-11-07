/*
 * On a Google Ảnh results page the extension opened itself (its address carries #reels-<request id>), hand the
 * photos' addresses to the background script. Pages the member opens by hand are left alone.
 */
(() => {
  const request = /[#&]reels-([a-z0-9-]+)/.exec(location.hash)?.[1];
  if (!request) {
    return;
  }
  const report = (tries) => {
    const photos = globalThis.reelsGoogleImages(document.documentElement.innerHTML);
    // The results arrive with the page; a slow page gets a few more seconds.
    if (photos.length === 0 && tries > 0) {
      setTimeout(() => report(tries - 1), 1000);
      return;
    }
    chrome.runtime.sendMessage({ type: "google-results", request, photos });
  };
  report(5);
})();
