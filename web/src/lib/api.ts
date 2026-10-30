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

export type VideoStatus = "draft" | "queued" | "writing" | "rendering" | "done" | "failed";

export type VideoRow = {
  id: number;
  topic: string;
  title: string;
  created_by: string;
  created_at: string;
  status: VideoStatus;
  status_label: string;
  mp4_outdated: boolean;
  rerender_failed: boolean;
  thumbnail_url: string | null;
};

export type JobInfo = {
  id: number;
  kind: "script" | "clone" | "render";
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  error: string | null;
  error_detail: string | null;
  created_by: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type SceneData = {
  id: number;
  is_title: boolean;
  text: string;
  seconds: number;
  keywords: string[];
  image_prompt: string;
  voice_text: string;
  /** Length of the narration made for the current voice text; null until a render has made it. */
  voice_seconds: number | null;
  voice_url: string | null;
  /** The scene's seconds, lengthened to fit its narration when that is longer. */
  fitted_seconds: number;
  has_image: boolean;
  image_error: string | null;
  image_url: string | null;
  preview_url: string | null;
  text_problem: string | null;
  blocking: string[];
  warnings: string[];
};

export type VideoDetail = VideoRow & {
  has_script: boolean;
  title_options: string[];
  caption: string;
  hashtags: string[];
  affiliates: string[];
  pinned_comment: string;
  self_review: string[];
  music_suggestions: string[];
  locked: boolean;
  active_job: JobInfo | null;
  failed_job: JobInfo | null;
  mp4: { url: string; download_url: string; seconds: number; render_seconds: number; rendered_at: string } | null;
  music: { url: string; name: string | null } | null;
  music_volume: number;
  voice_enabled: boolean;
  clone_of: { title: string; request: string } | null;
  title_scene: SceneData | null;
  scenes: SceneData[];
  video_blocking: string[];
  video_warnings: { field: string; message: string }[];
  can_render: boolean;
};

export type Knowledge = {
  script_prompt: string;
  clone_prompt: string;
  banned_words: string[];
  default_script_prompt: string;
  default_clone_prompt: string;
  default_banned_words: string[];
};

export type PixabayHit = { url: string; preview: string };

export type JobRow = {
  id: number;
  video_id: number;
  video_title: string;
  kind: JobInfo["kind"];
  kind_label: string;
  status: JobInfo["status"];
  created_by: string;
  created_at: string;
  started_at: string | null;
  duration_seconds: number | null;
  claude_calls: number;
  error: string | null;
};

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

/** Calls the API through the same-origin /api rewrite and turns every failure into an ApiError. */
export async function api<T>(path: string, method: Method = "GET", body?: unknown): Promise<T> {
  return send<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** One file per request: the Cloudflare proxy buffers the whole body, so files never go in batches. */
export async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser sets the multipart boundary itself.
  return send<T>(path, { method: "POST", body: form });
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, cache: "no-store" });
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
export function formatDateTime(iso: string): string {
  const part = Object.fromEntries(dateParts.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${part.day}/${part.month}/${part.year} ${part.hour}:${part.minute}`;
}

export function formatLastLogin(iso: string | null): string {
  return iso ? formatDateTime(iso) : "Chưa đăng nhập";
}

export function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err);
}
