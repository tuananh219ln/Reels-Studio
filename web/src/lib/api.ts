export const CONNECTION_MESSAGE = "Không kết nối được máy chủ, thử lại sau";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export type Me = {
  id: number;
  email: string;
  name: string;
  initial: string;
  must_change_password: boolean;
};

export type UserRow = {
  id: number;
  email: string;
  name: string;
  initial: string;
  is_active: boolean;
  last_login_at: string | null;
  active_sessions: number;
  is_me: boolean;
};

type Method = "GET" | "POST" | "PATCH";

/** Calls the API through the same-origin /api rewrite and turns every failure into an ApiError. */
export async function api<T>(path: string, method: Method = "GET", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "connection", CONNECTION_MESSAGE);
  }
  const data = await response.json().catch(() => null);
  if (response.ok) {
    return data as T;
  }
  if (data && typeof data.code === "string" && typeof data.message === "string") {
    if (data.code === "not_authenticated") {
      window.location.assign("/login");
    } else if (data.code === "password_change_required") {
      window.location.assign("/change-password");
    }
    throw new ApiError(response.status, data.code, data.message);
  }
  // The Next.js proxy answers without our JSON body when the API process is not running.
  throw new ApiError(response.status, "connection", CONNECTION_MESSAGE);
}

const dateParts = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Ho_Chi_Minh",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** dd/mm/yyyy hh:mm in Vietnam time; the API stores and sends UTC. */
export function formatLastLogin(iso: string | null): string {
  if (!iso) {
    return "Chưa đăng nhập";
  }
  const part = Object.fromEntries(dateParts.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${part.day}/${part.month}/${part.year} ${part.hour}:${part.minute}`;
}
