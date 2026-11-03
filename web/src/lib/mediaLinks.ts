/**
 * Photos and clips taken from other sites without downloading them first: a copied photo or a link pasted into a
 * scene, or a photo dragged from another tab. A link (a photo's, a video file's, a TikTok video's) is downloaded by
 * the api (POST /scenes/{id}/media-from-url); a copied photo, or a "data:" address (Google Ảnh's thumbnails), is
 * uploaded like a chosen file.
 */

/** Google Ảnh for the keyword, opened on tall photos (the 9:16 frame crops least of them). */
export function googleImagesUrl(keyword: string): string {
  const params = new URLSearchParams({ q: keyword, udm: "2", tbs: "iar:t" });
  return `https://www.google.com/search?${params.toString()}`;
}

/** TikTok's video search for the keyword; its videos are tall already. */
export function tiktokSearchUrl(keyword: string): string {
  return `https://www.tiktok.com/search/video?${new URLSearchParams({ q: keyword }).toString()}`;
}

/** The photo's own address when the link is a Google Ảnh result page (/imgres?imgurl=...), else the link itself. */
export function unwrapLink(link: string): string {
  try {
    const url = new URL(link);
    const imgurl = url.searchParams.get("imgurl");
    if (/(^|\.)google\.[a-z.]+$/.test(url.hostname) && url.pathname === "/imgres" && imgurl) {
      return imgurl;
    }
  } catch {
    // Not a full address: returned as typed, the api says what is wrong with it.
  }
  return link;
}

/** A link worth sending: an http(s) address or a data: photo. */
export function looksLikeLink(text: string): boolean {
  return /^https?:\/\/\S+$/i.test(text) || /^data:image\//i.test(text);
}

/**
 * Whether a link most likely holds a clip (a TikTok video, a video file) rather than a photo, to ask the right
 * question before it replaces what the scene has; the api decides from what it downloads.
 */
export function looksLikeClipLink(link: string): boolean {
  try {
    const url = new URL(link);
    return /(^|\.)tiktok\.com$/i.test(url.hostname) || /\.(mp4|mov|webm)$/i.test(url.pathname);
  } catch {
    return false;
  }
}

/** The photo's address in what was dragged from another tab: the <img> itself first, then the link. */
export function linkFromTransfer(transfer: DataTransfer): string | null {
  const html = transfer.getData("text/html");
  if (html) {
    const src = new DOMParser().parseFromString(html, "text/html").querySelector("img")?.getAttribute("src");
    if (src && looksLikeLink(src)) {
      return unwrapLink(src);
    }
  }
  const candidates = [
    ...transfer
      .getData("text/uri-list")
      .split(/\r?\n/)
      .filter((line) => line && !line.startsWith("#")),
    transfer.getData("text/plain").trim(),
  ];
  const link = candidates.find((item) => looksLikeLink(item));
  return link ? unwrapLink(link) : null;
}

/** A data: photo as a file, so it goes through the same checks and upload as a chosen one. */
export async function fileFromDataUrl(link: string): Promise<File> {
  const blob = await (await fetch(link)).blob();
  const extension = blob.type.split("/")[1]?.replace("jpeg", "jpg") || "img";
  return new File([blob], `anh-dan.${extension}`, { type: blob.type });
}
