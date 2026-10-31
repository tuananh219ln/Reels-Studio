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

export const config = {
  matcher: ["/", "/videos/:path*", "/users/:path*", "/knowledge/:path*", "/music/:path*", "/jobs/:path*", "/settings/:path*", "/change-password"],
};
