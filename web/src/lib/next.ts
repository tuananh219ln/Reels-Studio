/** Where the login and password pages go back to: only the MCP authorize request that sent the member to sign in
 * (`/login?next=...` from its "Đăng nhập Reels Studio" link). Anything else is ignored, so these pages can never
 * send a member to another site or page. */
const AUTHORIZE = "/api/mcp/oauth/authorize?";

export function nextAfterLogin(): string | null {
  const next = new URLSearchParams(window.location.search).get("next");
  // A same-origin path: it starts with one "/", so it can never be "//host" or "https://host".
  return next && next.startsWith(AUTHORIZE) ? next : null;
}

/** The same `next`, carried on to another page of the sign-in. */
export function withNext(path: string): string {
  const next = nextAfterLogin();
  return next ? `${path}?${new URLSearchParams({ next })}` : path;
}

/** After signing in: back to the authorize request (an API URL, so a full page load), or to the app. */
export function leaveSignIn(replace: (path: string) => void) {
  const next = nextAfterLogin();
  if (next) {
    window.location.assign(next);
  } else {
    replace("/videos");
  }
}
