/*
 * Reading a Google Ảnh results page (also loaded by web/e2e/google-extension.spec.ts, so it stays a plain script).
 * The page carries each result's original photo as ["https://…", height, width] inside its scripts; Google's own
 * thumbnails (gstatic) are left out, and so are photos too small for a 9:16 frame.
 */
globalThis.reelsGoogleImages = function reelsGoogleImages(html, limit = 20, minSide = 500) {
  const pattern = /\["(https?:\/\/[^"]+?)",(\d{2,5}),(\d{2,5})\]/g;
  const seen = new Set();
  const found = [];
  let match;
  while ((match = pattern.exec(html)) && found.length < limit) {
    let url;
    try {
      // The addresses are JSON strings: "=" arrives as =.
      url = JSON.parse(`"${match[1]}"`);
    } catch {
      continue;
    }
    const height = Number(match[2]);
    const width = Number(match[3]);
    let host;
    try {
      host = new URL(url).hostname;
    } catch {
      continue;
    }
    if (/(^|\.)(gstatic|google|googleusercontent|ggpht)\.com$/.test(host) || seen.has(url)) {
      continue;
    }
    seen.add(url);
    if (Math.min(width, height) >= minSide) {
      found.push({ url, width, height });
    }
  }
  return found;
};
