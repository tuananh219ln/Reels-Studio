import { NextResponse, type NextRequest } from "next/server";

export const SESSION_COOKIE = "reels_session";

// Optimistic check before any app page renders: without a session cookie there is nothing to show.
// The API still validates the session on every request.
export function proxy(request: NextRequest) {
  if (!request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

// Every page except the login screen and the public privacy and terms pages. New pages are covered without
// touching this list: only /login, /privacy and /terms (exactly), the /api proxy, Next.js assets and files with an
// extension (favicon, images) are left out.
export const config = {
  matcher: ["/((?!login|privacy$|terms$|api/|_next/|.*\\..*).*)"],
};
