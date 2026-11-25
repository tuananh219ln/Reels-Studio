/*
 * The second Facebook account a competitor scan runs as ("Phân tích đối thủ"), signed in by its cookies. The member
 * pastes them once on the extension's options page; they stay in this Chrome (chrome.storage.local), are never sent
 * to Reels Studio's server, and are set only in the incognito window a scan opens, so the member's own Facebook in
 * their normal windows is never touched. Closing the last incognito window drops them from that window's store.
 *
 * Removing the extension deletes chrome.storage.local, so the "Đối thủ" page keeps a copy in its own storage in this
 * same Chrome (never on the server): an extension installed again takes it back (syncScanAccount). "Xóa" on the
 * options page leaves a mark, so a copy older than it is dropped, never restored.
 */

const ACCOUNT_KEY = "scanAccount";
const REMOVED_KEY = "scanAccountRemovedAt";
// Cookies Facebook sets HttpOnly; the rest are readable by its pages, as in a real browser.
const HTTP_ONLY = new Set(["xs", "fr", "datr", "sb", "spin", "ps_l", "ps_n"]);
const COOKIE_DAYS = 30;

/**
 * The cookies in a pasted text: a "Cookie:" header ("c_user=1; xs=2"), or the JSON list that cookie-export extensions
 * (Cookie-Editor, EditThisCookie) save. Only facebook.com cookies of a JSON list are kept.
 */
function parseScanCookies(text) {
  const raw = String(text || "").trim();
  let cookies = [];
  if (raw.startsWith("[") || raw.startsWith("{")) {
    let list;
    try {
      list = JSON.parse(raw);
    } catch {
      throw new Error("JSON cookie không đọc được");
    }
    list = Array.isArray(list) ? list : list.cookies || [];
    cookies = list
      .filter((item) => item && item.name && item.value !== undefined)
      .filter((item) => !item.domain || String(item.domain).replace(/^\./, "").endsWith("facebook.com"))
      .map((item) => ({ name: String(item.name), value: String(item.value) }));
  } else {
    cookies = raw
      .replace(/^cookie:\s*/i, "")
      .split(";")
      .map((part) => part.trim())
      .filter((part) => part.includes("="))
      .map((part) => {
        const at = part.indexOf("=");
        return { name: part.slice(0, at).trim(), value: part.slice(at + 1).trim() };
      });
  }
  cookies = cookies.filter((cookie) => /^[A-Za-z0-9_.-]{1,64}$/.test(cookie.name) && cookie.value.length <= 4096);
  const userId = cookies.find((cookie) => cookie.name === "c_user")?.value;
  if (!userId || !/^\d{5,30}$/.test(userId) || !cookies.some((cookie) => cookie.name === "xs" && cookie.value)) {
    throw new Error("Thiếu cookie c_user hoặc xs: hãy copy đủ cookie của facebook.com khi đang đăng nhập tài khoản phụ");
  }
  return { cookies, userId };
}

async function saveScanAccount(text) {
  const { cookies, userId } = parseScanCookies(text);
  await chrome.storage.local.set({ [ACCOUNT_KEY]: { cookies, userId, savedAt: new Date().toISOString() } });
  await chrome.storage.local.remove(REMOVED_KEY);
  return { userId };
}

async function clearScanAccount() {
  await chrome.storage.local.remove(ACCOUNT_KEY);
  await chrome.storage.local.set({ [REMOVED_KEY]: new Date().toISOString() });
}

/**
 * The page's copy against the saved account, when the page asks for the status. No account saved and a copy that
 * passes parseScanCookies and is newer than the last "Xóa": the copy is saved again (the extension was removed and
 * installed). Returns what the page should do with its copy: `backup` (the saved account, when the copy is missing or
 * older) or `forget` (no account, or the copy predates "Xóa").
 */
async function syncScanAccount(copy) {
  let account = await scanAccount();
  const removedAt = (await chrome.storage.local.get(REMOVED_KEY))[REMOVED_KEY] || null;
  const savedAt = copy && typeof copy.savedAt === "string" ? copy.savedAt : "";
  if (!account && copy && Array.isArray(copy.cookies) && savedAt && !(removedAt && savedAt <= removedAt)) {
    try {
      const header = copy.cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; ");
      const { cookies, userId } = parseScanCookies(header);
      account = { cookies, userId, savedAt };
      await chrome.storage.local.set({ [ACCOUNT_KEY]: account });
    } catch {
      account = null;
    }
  }
  if (!account) {
    return copy ? { forget: true } : {};
  }
  return savedAt === account.savedAt ? {} : { backup: account };
}

async function scanAccount() {
  return (await chrome.storage.local.get(ACCOUNT_KEY))[ACCOUNT_KEY] || null;
}

/** What the "Đối thủ" page shows: whose cookies are saved, and whether the extension may open incognito windows. */
async function scanAccountStatus() {
  const account = await scanAccount();
  return {
    userId: account ? account.userId : null,
    savedAt: account ? account.savedAt : null,
    incognito: await chrome.extension.isAllowedIncognitoAccess(),
  };
}

/** Signs the incognito tab's cookie store in as the saved account: its old facebook.com cookies go first. */
async function signInScanTab(tabId, account) {
  const stores = await chrome.cookies.getAllCookieStores();
  const store = stores.find((candidate) => candidate.tabIds.includes(tabId));
  if (!store) {
    throw new Error("Không tìm thấy kho cookie của cửa sổ ẩn danh");
  }
  for (const old of await chrome.cookies.getAll({ domain: "facebook.com", storeId: store.id })) {
    const host = old.domain.replace(/^\./, "");
    await chrome.cookies.remove({ url: `https://${host}${old.path}`, name: old.name, storeId: store.id });
  }
  const expires = Math.floor(Date.now() / 1000) + COOKIE_DAYS * 24 * 3600;
  for (const cookie of account.cookies) {
    await chrome.cookies.set({
      url: "https://www.facebook.com/",
      domain: ".facebook.com",
      path: "/",
      name: cookie.name,
      value: cookie.value,
      secure: true,
      httpOnly: HTTP_ONLY.has(cookie.name),
      sameSite: "no_restriction",
      expirationDate: expires,
      storeId: store.id,
    });
  }
}
