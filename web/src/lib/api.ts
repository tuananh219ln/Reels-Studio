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

export type VideoStatus = "draft" | "queued" | "writing" | "imaging" | "rendering" | "publishing" | "done" | "failed";

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
  kind: "script" | "clone" | "render" | "publish" | "image";
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
  /** The same search terms in English, for the Western stock libraries (Pixabay, Pexels). */
  keywords_en: string[];
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
  /** A clip shown instead of the photo; the scene has one or the other. */
  video: { url: string; seconds: number; start: number } | null;
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
  /** The video's own settings from its "Thiết lập" tab. */
  options: VideoOptions;
  /** The Pages in use, connected on /fanpages. */
  fanpages: { id: number; name: string }[];
  /** The post to the Facebook Page; `pending` until the publish job has finished. */
  publication: {
    status: "pending" | "scheduled" | "published";
    fanpage: string | null;
    scheduled_at: string | null;
    url: string | null;
  } | null;
  knowledge_topic: string | null;
  /** The provider and model that wrote the script, e.g. "DeepSeek · deepseek-chat". */
  script_by: string | null;
  clone_of: { title: string; request: string } | null;
  title_scene: SceneData | null;
  scenes: SceneData[];
  video_blocking: string[];
  video_warnings: { field: string; message: string }[];
  can_render: boolean;
};

export type KnowledgeTopic = {
  id: number;
  name: string;
  script_prompt: string;
  clone_prompt: string;
  banned_words: string[];
  video_count: number;
};

export type Fanpage = {
  id: number;
  page_id: string;
  name: string;
  token_tail: string;
  active: boolean;
  updated_at: string;
  updated_by: string | null;
};

/** A video's settings, each a named preset (api video_options.DEFAULTS). */
export type VideoOptions = {
  voice_id: string;
  voice_speed: "slow" | "normal" | "fast";
  voice_volume: number;
  ducking: boolean;
  transition: "fade" | "cut" | "slide";
  motion: "zoom_in" | "zoom_out" | "pan" | "static";
  zoom: "light" | "medium" | "strong";
  text_style: "yellow" | "white" | "dark" | "red" | "none";
  text_color: "auto" | "white" | "black" | "yellow" | "red";
  title_style: "same" | "yellow";
  captions: "off" | "phrase" | "word";
};

/** What a new video starts with (Cài đặt › Thiết lập mặc định). */
export type VideoDefaults = VideoOptions & { voice_enabled: boolean; music_volume: number };

export type Voice = { id: string; name: string; description: string; preview_url: string | null };

/** One LLM provider on /settings/ai. Its API key never comes back: only where it comes from and its last characters. */
export type LlmProvider = {
  id: string;
  name: string;
  kind: "anthropic" | "openai";
  needs_key: boolean;
  key_source: "saved" | "env" | null;
  key_tail: string | null;
  key_unreadable: boolean;
  base_url: string;
  default_base_url: string;
  model: string;
  model_suggestions: string[];
  effective_base_url: string;
  effective_model: string;
  problem: string | null;
  active: boolean;
  updated_at: string | null;
  updated_by: string | null;
};

export type LlmSettings = { active: string; providers: LlmProvider[] };

/** The provider and model a script job would use now. */
export type ActiveLlm = { provider: string; name: string; model: string; problem: string | null };

/** A Page a pasted token manages. */
export type FanpageChoice = { page_id: string; name: string; can_post: boolean };

export type Knowledge = {
  topics: KnowledgeTopic[];
  default_script_prompt: string;
  default_clone_prompt: string;
};

export type MusicTrack = {
  id: number;
  name: string;
  topics: string[];
  mood: string;
  license_note: string;
  url: string;
  created_by: string;
  created_at: string;
};

/** The api's fixed lists that tag every track. */
export type MusicOptions = { topics: string[]; moods: string[] };

/** One "Chọn từ Pixabay" result: `preview` is only a thumbnail to show; `url` is the full photo the server stores. */
export type PixabayHit = { url: string; preview: string };

export type StockSource = { id: string; label: string; available: boolean; clips?: boolean };

/** A stock video clip in the picker's "Video" mode; `preview` is a still shown straight from the source. */
export type ClipHit = { id: string; preview: string; url: string; seconds: number };

export type AffiliateProduct = {
  id: number;
  knowledge_topic_id: number;
  topic: string;
  name: string;
  url: string;
  shop_name: string;
  shop_type: string;
  shop_type_label: string;
  rating: number;
  sold: number;
  price: number;
  commission_rate: number;
  expected_commission: number;
  status: "draft" | "approved";
  checked_at: string | null;
  checked_by: string | null;
  /** Why it cannot be approved; empty when it can. */
  problems: string[];
};

export type AffiliateOptions = {
  shop_types: { value: string; label: string }[];
  topics: { id: number; name: string }[];
};

/** A posted reel and the products whose links go in its pinned comment. */
export type AffiliateVideo = {
  id: number;
  title: string;
  reel_url: string | null;
  published_at: string;
  suggestions: string[];
  pinned_comment: string;
  products: Pick<AffiliateProduct, "id" | "name" | "url" | "status" | "problems">[];
};

/** A reel on Facebook, or waiting there for its time. */
export type PostRow = {
  video_id: number;
  title: string;
  status: "scheduled" | "published";
  fanpage: string | null;
  /** When it went live, or goes live. */
  at: string;
  url: string | null;
  created_by: string;
};

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
  image_calls: number;
  /** "DeepSeek · deepseek-chat" for a script or clone job; null for other jobs and older ones. */
  llm: string | null;
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
export async function upload<T>(path: string, file: File, fields: Record<string, string | string[]> = {}): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  for (const [name, value] of Object.entries(fields)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      form.append(name, item);
    }
  }
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
    // A full page load on purpose: this helper runs outside components (no router), and leaving the app
    // must drop every client state of the expired session.
    if (data.code === "not_authenticated") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    } else if (data.code === "password_change_required") {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
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
