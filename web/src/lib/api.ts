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

export type VideoStatus =
  | "draft"
  | "queued"
  | "writing"
  | "imaging"
  | "finding"
  | "voicing"
  | "rendering"
  | "publishing"
  | "unpublishing"
  | "checking"
  | "done"
  | "failed";

/** Where a video is made for: a Facebook reel (Shopee links), or TikTok (posted by hand, TikTok Shop's cart). */
export type VideoPlatform = "facebook" | "tiktok";

export type VideoRow = {
  id: number;
  topic: string;
  title: string;
  platform: VideoPlatform;
  /** The video a TikTok version was made from; the list shows the version on that video's card. */
  variant_of_id: number | null;
  /** A TikTok post of it was recorded ("Đã đăng tay"). */
  tiktok_posted: boolean;
  /** A TikTok version was made from it; a Facebook clone ("Nhân bản", a version for another Page) was made from it. */
  has_tiktok_version: boolean;
  cloned: boolean;
  created_by: string;
  created_at: string;
  status: VideoStatus;
  status_label: string;
  mp4_outdated: boolean;
  rerender_failed: boolean;
  thumbnail_url: string | null;
  knowledge_topic: string | null;
  /** The 30-day plan day of the idea it was made from. */
  plan_day: number | null;
  /** Its Facebook posts in one line; null when none is out or set for later. */
  post: VideoRowPost | null;
};

/** A video's posts on the list: views are every live post's latest reading added up; the 48-hour numbers are of
 * its post with the most views. */
export type VideoRowPost = {
  state: "posted" | "scheduled";
  /** The post with the most views, or the next one set for later. */
  fanpage: string;
  /** Every Page it is out on or set for. */
  fanpages: string[];
  pages: number;
  at: string;
  views: number | null;
  shares: number | null;
  share_rate: number | null;
  /** Whether share/view reaches the team's goal (analytics.SHARE_GOAL). */
  share_met: boolean | null;
  /** Null while its Page has fewer than 5 posts measured at 48 hours. */
  times_median: number | null;
};

export type JobInfo = {
  id: number;
  kind:
    | "script"
    | "clone"
    | "learn"
    | "render"
    | "publish"
    | "unpublish"
    | "check"
    | "image"
    | "photos"
    | "voice"
    | "revise";
  /** The one scene an image job makes a photo for; null for every other job. */
  scene_id: number | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  error: string | null;
  error_detail: string | null;
  created_by: string | null;
  started_at: string | null;
  finished_at: string | null;
};

/** A text or sticker layer over a scene (reels_render.layers): its own seconds, place, look and entrance. */
export type SceneLayer = {
  id: number;
  kind: "text" | "sticker";
  text: string;
  sticker: string;
  /** Seconds into its scene. */
  start: number;
  seconds: number;
  /** Its centre in the 1080×1920 frame; the picture is kept inside the frame. */
  x: number;
  y: number;
  size: string;
  style: string;
  animation: string;
  /** The exact picture the render lays on. */
  image_url: string;
};

/** A sound effect heard from a second of its scene (reels_render.sounds), made by FFmpeg. */
export type SceneSound = {
  id: number;
  sound: string;
  /** Seconds into its scene. */
  start: number;
  volume: string;
  /** The sound as the render makes it. */
  url: string;
};

/** A "Mẫu dựng": the app's own ("app") or the team's, with what it does in Vietnamese lines. */
export type EditTemplate = {
  id: "app" | number;
  name: string;
  builtin: boolean;
  summary: string[];
};

export type EditTemplates = {
  templates: EditTemplate[];
  /** The template put on every new video; null for none. */
  default: "app" | number | null;
};

/** A member's comment at a second of the video ("Góp ý"), sent to the AI with "Nhờ AI sửa". */
export type VideoNote = {
  id: number;
  /** Seconds from the video's start. */
  at: number;
  /** The scene playing at that second now. */
  scene_id: number | null;
  text: string;
  /** open: not sent yet; sent: waiting for the AI; done: answered. */
  status: "open" | "sent" | "done";
  reply: string;
  created_by: string;
  created_at: string;
};

export type SceneData = {
  id: number;
  video_id: number;
  is_title: boolean;
  text: string;
  seconds: number;
  /** "Tự khớp lời đọc": once the narration is made, the seconds follow it; typing them turns it off. */
  seconds_auto: boolean;
  keywords: string[];
  /** The same search terms in English, for the Western stock libraries (Pixabay, Pexels). */
  keywords_en: string[];
  image_prompt: string;
  voice_text: string;
  /** What the narration reads (videos.spoken): the voice text, else the cleaned on-screen text; "" when silent. */
  spoken_text: string;
  /** Length of the narration made for the current voice text; null until a render has made it. */
  voice_seconds: number | null;
  voice_url: string | null;
  /** The scene's seconds, lengthened to fit its narration when that is longer. */
  fitted_seconds: number;
  has_image: boolean;
  /** The photo was made by AI (an image job), so the card offers "Tạo lại ảnh AI". */
  image_ai: boolean;
  /** Picked by "Tự tìm ảnh" after the script and not yet changed or kept by a member. */
  image_auto: boolean;
  image_error: string | null;
  image_url: string | null;
  /** A clip shown instead of the photo; the scene has one or the other. */
  video: { url: string; seconds: number; start: number; speed: number } | null;
  preview_url: string | null;
  /** Where a member dragged this scene's text box (its centre in the 1080×1920 frame); null: not moved. */
  text_position: [number, number] | null;
  /** Where the box goes after all: its own place, the video's place for content scenes, or null (the template's). */
  placed_at: [number, number] | null;
  /** The frame without text and the exact box image, which the box is dragged with. */
  frame_url: string | null;
  textbox_url: string | null;
  text_problem: string | null;
  /** The studio's effects (reels_render.effects): the transition into this scene, null for the video's one. */
  transition: string | null;
  /** Its colour preset, null for the picture as shot. The title scene has neither. */
  color: string | null;
  /** Text and sticker layers over the scene, in the order they are laid on (the last on top). */
  layers: SceneLayer[];
  sounds: SceneSound[];
  /** The music's level during the scene ("off", "low", "high"); null: the video's. */
  music_level: string | null;
  blocking: string[];
  warnings: string[];
};

export type VideoDetail = VideoRow & {
  has_script: boolean;
  /** "Tự viết": a member wrote the script; no AI wrote it or reviewed its safety. */
  hand_written: boolean;
  title_options: string[];
  caption: string;
  hashtags: string[];
  /** What a post sends: the caption, then the hashtags it does not already hold. */
  post_text: string;
  affiliates: string[];
  /** The products attached to the video: Shopee links in the reel's comment, or TikTok Shop's cart. */
  affiliate_product_ids: number[];
  /** The Facebook video this TikTok version was made from, and the versions made from this one. */
  variant_of: VideoLink | null;
  variants: VideoLink[];
  /** TikTok posts made by hand and recorded with their link, newest first. */
  tiktok_posts: TikTokPost[];
  /** Shopee's product suggestions for the video (the worker searches with a member's own account). */
  suggest: { state: "idle" | "pending" | "failed"; error: string | null; at: string | null };
  pinned_comment: string;
  self_review: string[];
  music_suggestions: string[];
  locked: boolean;
  active_job: JobInfo | null;
  failed_job: JobInfo | null;
  mp4: { url: string; download_url: string; seconds: number; render_seconds: number; rendered_at: string } | null;
  music: { url: string; name: string | null } | null;
  music_volume: number;
  /** Where in the song the music starts, in seconds. */
  music_start: number;
  notes: VideoNote[];
  /** Made with "AI gợi ý hiệu ứng". */
  ai_effects: boolean;
  voice_enabled: boolean;
  /** The video's own settings from its "Thiết lập" tab. */
  options: VideoOptions;
  /** The Pages in use, connected on /fanpages; `owner` is the member whose Page it is. */
  fanpages: { id: number; name: string; owner: string | null; error: string | null }[];
  /** The newest post still on its way or on Facebook; `pending` until the publish job has finished. */
  publication: Post | null;
  /** Every post of the video, newest first, cancelled and deleted ones included. */
  publications: Post[];
  /** The Pages that already hold the current MP4. */
  posted_fanpage_ids: number[];
  knowledge_topic: string | null;
  /** The provider and model that wrote the script, e.g. "DeepSeek · deepseek-chat". */
  script_by: string | null;
  clone_of: { title: string; request: string } | null;
  /** "Từ video mẫu": the sample video the script is learned from; null for other videos. */
  reference: VideoSample | null;
  /** The 30-day plan idea the video was made from. */
  plan_idea:
    | (PlanIdeaFields & {
        id: number;
        knowledge_topic_id: number;
        /** When the plan means the video to go out (its day, at the group's posting time); null once past. */
        suggested_post_at: string | null;
      })
    | null;
  title_scene: SceneData | null;
  scenes: SceneData[];
  video_blocking: string[];
  video_warnings: { field: string; message: string }[];
  can_render: boolean;
};

/** "Từ video mẫu": the way a video is learned from its sample (api reference.MODES). */
export type SampleMode = "quick" | "twostep" | "review" | "reuse";

/** A still of a sample video, with what the AI wrote it shows. */
export type SampleFrame = { second: number; note: string; url: string };

export type VideoSample = {
  /** null once the sample was deleted; the video keeps its script and clips. */
  id: number | null;
  mode: SampleMode;
  mode_label: string;
  source_name: string | null;
  source_url: string | null;
  seconds: number | null;
  transcript: string;
  analysis: string;
  frames: SampleFrame[];
  /** Way "review": the analysis is written and waits for a member before "Viết kịch bản". */
  awaiting_review: boolean;
};

/** A sample video learned before, for "Dùng mẫu đã học". */
export type SampleSummary = {
  id: number;
  source_name: string;
  source_url: string | null;
  seconds: number | null;
  analyzed: boolean;
  analysis: string;
  cover_url: string | null;
  video_count: number;
  created_by: string;
  created_at: string;
};

export type VideoLink = { id: number; title: string; platform: VideoPlatform };

/** "Đã dùng trong nhóm": photos and clips of the other videos in a scene's topic group, best match first. */
export type GroupMedia = {
  items: {
    scene_id: number;
    video_id: number;
    video_title: string;
    text: string;
    keywords: string[];
    kind: "photo" | "clip";
    url: string;
  }[];
  /** How many pictures the group's other videos hold, matching or not. */
  total: number;
};

export type TikTokPost = { id: number; url: string; account: string | null; at: string; created_by: string };

export type KnowledgeTopic = {
  id: number;
  name: string;
  script_prompt: string;
  clone_prompt: string;
  /** "Prompt sửa theo góp ý"; "" uses the default. */
  revise_prompt: string;
  banned_words: string[];
  /** "Gợi ý tìm ảnh": what the group's photos show, added to the script prompts for the search keywords. */
  photo_hint: string;
  /** "Từ video mẫu": empty means the default prompt. */
  learn_prompt: string;
  analyze_prompt: string;
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
  /** The member whose Page it is; `mine` when that is the signed-in member. */
  owner: { id: number; name: string } | null;
  mine: boolean;
  /** The Shopee account whose links its comments carry, shown only to its owner. */
  shopee_account: { id: number; name: string; usable: boolean } | null;
  /** The worker's last check of the token (api fanpages.check). */
  check: {
    checked_at: string | null;
    error: string | null;
    pending: boolean;
    followers: number | null;
    followers_this_week: number | null;
  };
  /** Posts still waiting for their time on Facebook. */
  scheduled_posts: number;
  /** Every post ever made to the Page; a Page with any cannot be deleted, only stopped. */
  posts: number;
  /** Page Insights summed over the last 7 days, and what went wrong at the last reading. */
  insights: {
    last_7_days: { views: number | null; reach: number | null; engagements: number | null };
    error: string | null;
  };
};

/** A number of a period with the same of the period before it; `change` is a fraction (0.25 is +25 %), null when
 * there is nothing to compare with. */
export type DashboardFigure = { value: number | null; previous: number | null; change: number | null };

export type DashboardVideo = { id: number; title: string; thumbnail_url: string | null };

/** One Page's dashboard over the last `days` days in Vietnam time (api GET /fanpages/{id}/dashboard). */
export type PageDashboard = {
  page: {
    id: number;
    page_id: string;
    name: string;
    active: boolean;
    owner: { id: number; name: string } | null;
    token_tail: string;
    check: Fanpage["check"];
    insights_error: string | null;
  };
  days: number;
  start: string;
  end: string;
  /** Each day of the period, oldest first; `posts` counts the app's posts that went live that day. */
  series: {
    day: string;
    views: number | null;
    reach: number | null;
    engagements: number | null;
    followers: number | null;
    posts: number;
  }[];
  totals: Record<"views" | "reach" | "engagements" | "followers_gain" | "posts", DashboardFigure>;
  followers: number | null;
  /** Summed from the latest reading of the period's posts: close to, not exactly, what the Page earned then. */
  post_numbers: Record<"reactions" | "comments" | "shares" | "avg_watch_seconds", DashboardFigure>;
  latest_post: {
    id: number;
    remote_id: string | null;
    live_at: string;
    video: DashboardVideo;
    numbers: {
      views: number | null;
      reach: number | null;
      reactions: number | null;
      comments: number | null;
      shares: number | null;
      avg_watch_seconds: number | null;
      measured_at: string;
    } | null;
  } | null;
  /** The next week: posts waiting for their time, and posting times no post takes yet. */
  upcoming: {
    posts: { id: number; status: string; scheduled_at: string; video: DashboardVideo }[];
    free_slots: string[];
    post_times: string[];
  };
};

/** One post the app made to a Page, on the dashboard's "Nội dung" tab (api page_dashboard.content). */
export type PageContentPost = {
  id: number;
  /** "deleted": taken off Facebook after going live. */
  status: "published" | "deleted";
  live_at: string;
  closed_at: string | null;
  /** The reel on Facebook; null once it is taken down. */
  url: string | null;
  video: DashboardVideo;
  /** The latest reading; null until the worker has read the post. */
  numbers: {
    views: number | null;
    reach: number | null;
    reactions: number | null;
    comments: number | null;
    shares: number | null;
    avg_watch_seconds: number | null;
    /** Follows the reel brought the Page. */
    followers: number | null;
    measured_at: string;
  } | null;
  views_48h: number | null;
  /** The 48-hour views as a multiple of the Page's median; null until the Page has enough measured posts. */
  times_median: number | null;
  /** "Cập nhật view" takes only a reel that is on Facebook. */
  can_refresh: boolean;
  /** A reading was asked for and the worker has not run it yet. */
  pending: boolean;
  error: string | null;
};

export type PageContent = {
  days: number;
  start: string;
  end: string;
  median: { views: number | null; samples: number; min_samples: number };
  posts: PageContentPost[];
};

/** A video's settings, each a named preset or a level (api video_options.DEFAULTS). */
export type VideoOptions = {
  voice_id: string;
  /** Reading speed, a tempo factor from 0.7 to 1.3 in steps of 0.05 (api tts.MIN_SPEED, MAX_SPEED). */
  voice_speed: number;
  voice_volume: number;
  ducking: boolean;
  transition: "fade" | "cut" | "slide";
  motion: "zoom_in" | "zoom_out" | "pan" | "static";
  zoom: "light" | "medium" | "strong";
  /** "box": a team box style's copied colours; yellow, white, dark and red are kept for older videos. */
  text_style: "yellow" | "white" | "dark" | "red" | "box" | "none";
  /** "auto", a named colour (older videos) or "#RRGGBB". */
  text_color: string;
  title_style: "same" | "yellow";
  /** The box's colour, or the outline's without a box: "auto" or "#RRGGBB". */
  box_color: string;
  /** The *marked* words' colour: "auto" or "#RRGGBB". */
  accent_color: string;
  box_opacity: "auto" | "solid" | "soft" | "clear" | "none";
  /** The title scene's own look, like the five above; "same" follows the scenes (or title_style "yellow"). */
  title_text_style: "same" | VideoOptions["text_style"];
  title_text_color: string;
  title_box_color: string;
  title_accent_color: string;
  title_box_opacity: VideoOptions["box_opacity"];
  captions: "off" | "phrase" | "word";
  /** The text box's size ("Cỡ chữ"): the content scenes' and the title's; "large" is the original template. */
  text_size: "large" | "medium" | "small";
  title_text_size: "large" | "medium" | "small";
  /** The content scenes' text box centre [x, y]; null: where the template puts it. A scene's own wins. */
  text_position: [number, number] | null;
};

/** One of the team's text box styles (Cài đặt, shared); a video copies its colours. */
export type TextBoxStyle = {
  id: string;
  name: string;
  box_color: string;
  box_opacity: "solid" | "soft" | "clear" | "none";
  text_color: string;
  accent_color: string;
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
  default_learn_prompt: string;
  default_analyze_prompt: string;
  default_revise_prompt: string;
};

/** What a 30-day plan idea says; `topic` becomes the video's Chủ đề. A null day is the Backlog. */
export type PlanIdeaFields = { day: number | null; topic: string; pain_group: string; pain: string; hook: string };

export type PlanItemStatus = "idea" | "started" | "scripted" | "done" | "scheduled" | "posted";

export type PlanItem = PlanIdeaFields & {
  id: number;
  knowledge_topic_id: number;
  position: number;
  status: PlanItemStatus;
  status_label: string;
  video_id: number | null;
  /** When its post went out or is set to. */
  post_at: string | null;
  /** When the plan means it to go out; null in the Backlog, without a start date, or once past. */
  suggested_post_at: string | null;
  /** Its video's Facebook posts that went live, with their 48-hour numbers (only on GET /plans/{id}). */
  posts?: PlanPost[];
};

/** A post's 48-hour numbers on a plan card; all null until the 48-hour reading exists. */
export type PlanPost = {
  publication_id: number;
  fanpage_name: string;
  views: number | null;
  shares: number | null;
  share_rate: number | null;
  /** Views over the Page's 60-day median, rounded to 0.1; null while the Page has fewer than 5 measured posts. */
  times_median: number | null;
  median_views: number | null;
  samples: number;
  measured_at: string | null;
};

/** An imported file or the AI's draft, shown before it replaces the plan. */
export type PlanPreview = { ideas: PlanIdeaFields[]; errors: string[]; warnings: string[]; can_backlog?: boolean };

export type Plan = {
  topic_id: number;
  name: string;
  start_date: string | null;
  /** Which plan day today is: below 1 before the start, above 30 after the end; null without a start date. */
  today_day: number | null;
  per_day: number;
  /** "HH:MM": the n-th idea of a day is suggested to go out at the n-th time. */
  post_times: string[];
  prompt: string;
  default_prompt: string;
  /** The 30 days, then the Backlog (day null). */
  items: PlanItem[];
  /** Ideas of the 30 days that already have a video. */
  made: number;
  /** "Tạo bằng AI" still queued or running, or the last one when it failed. */
  job: { id: number; status: JobInfo["status"]; error: string | null; error_detail: string | null } | null;
  draft: (PlanPreview & { job_id: number; created_at: string }) | null;
  /** The share/view goal the cards compare against. */
  share_goal: number;
  /** How many videos the group's trial counts towards; null: no "Tiến độ verdict" banner. */
  video_target: number | null;
  /** Videos made with this topic group. */
  video_count: number;
};

/** A topic group whose plan has a today, for "Tạo video" and the progress banner. */
export type PlanToday = {
  topic_id: number;
  name: string;
  day: number;
  ideas: PlanItem[];
  /** The last day, from today on, whose ideas all have a video; null when today's do not. */
  prepared_through: number | null;
  topics: string[];
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

/** A visitor's comment under one of the app's reels ("Bình luận"; api routes_comments.py). */
export type PageCommentRow = {
  id: number;
  /** open: waits for an answer; sending: a reply or hide waits for the worker; answered, hidden, dismissed. */
  state: "open" | "sending" | "answered" | "hidden" | "dismissed";
  author: string;
  message: string;
  created_at: string;
  reply_text: string | null;
  error: string | null;
  handled_by: string | null;
  url: string;
  post: {
    id: number;
    video_id: number;
    title: string;
    fanpage: string | null;
    fanpage_id: number | null;
    reel_url: string | null;
  };
};

export type PageComments = {
  comments: PageCommentRow[];
  /** Pages whose comments could not be read, with why. */
  read_errors: { fanpage: string; error: string }[];
  read_at: string | null;
};

export type ProductPlatform = "shopee" | "tiktok_shop";

export type AffiliateProduct = {
  id: number;
  knowledge_topic_id: number;
  topic: string;
  platform: ProductPlatform;
  platform_label: string;
  name: string;
  /** The link a member pasted; products found through Shopee's API have none (each Page gets its own). */
  url: string | null;
  page_url: string | null;
  image_url: string | null;
  from_shopee_api: boolean;
  commission_end_at: string | null;
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
  /** A pasted link or an imported row the worker is reading from Shopee ("pending"), or could not read ("failed"). */
  lookup: "pending" | "failed" | null;
  lookup_error: string | null;
};

export type AffiliateOptions = {
  platforms: { value: ProductPlatform; label: string }[];
  shop_types: Record<ProductPlatform, { value: string; label: string }[]>;
  topics: { id: number; name: string }[];
  /** Some member has a Shopee account with App ID, so a pasted link is filled in by itself. */
  shopee_lookup: boolean;
};

/** What "Nhập file" did with Shopee Affiliate's file. */
export type AffiliateImport = {
  added: number;
  updated: number;
  errors: { row: number; message: string }[];
  /** The worker will read stars, sales and the shop's type from Shopee. */
  lookup: boolean;
};

/** A posted reel and the products whose links go in its pinned comment. */
export type AffiliateVideo = {
  id: number;
  title: string;
  platform: VideoPlatform;
  reel_url: string | null;
  published_at: string;
  suggestions: string[];
  pinned_comment: string;
  products: Pick<AffiliateProduct, "id" | "name" | "url" | "status" | "problems">[];
};

/** Shopee's suggestions for a video, grouped by its product ideas. */
export type AffiliateSuggestions = {
  state: "idle" | "pending" | "failed";
  error: string | null;
  at: string | null;
  /** `pasted`: the links a member pasted on the video ("Dán link aff"), kept when a new search replaces the rest. */
  keywords: { keyword: string; products: AffiliateProduct[]; pasted: boolean }[];
  attached_ids: number[];
};

/** A member's own affiliate account; nobody else sees it, and the Secret never comes back. */
export type AffiliateAccount = {
  id: number;
  platform: "shopee" | "tiktok";
  platform_label: string;
  name: string;
  app_id: string | null;
  secret_tail: string | null;
  profile_url: string | null;
  active: boolean;
  report_read_at: string | null;
  report_error: string | null;
};

/** The member's own Shopee orders, by video and Page. */
export type AffiliateRevenue = {
  days: number;
  orders: number;
  commission: number;
  lines: {
    video_id: number | null;
    title: string | null;
    fanpage: string | null;
    orders: number;
    commission: number;
  }[];
  accounts: AffiliateAccount[];
};

export type PostStatus = "pending" | "scheduled" | "published" | "cancelled" | "deleted";

/** One post of a video to a Fanpage. */
export type Post = {
  id: number;
  status: PostStatus;
  fanpage: string | null;
  scheduled_at: string | null;
  /** When it went live, or goes live. */
  at: string;
  url: string | null;
  created_by: string;
  /** When and by whom it was cancelled or deleted; `closed_by` is null when a check found it so on Facebook. */
  closed_at: string | null;
  closed_by: string | null;
  metrics: PostMetrics;
  /** The affiliate comment the worker writes under the reel (api post_comments.payload). */
  comment: {
    state: "off" | "waiting" | "pending" | "done" | "failed";
    auto: boolean;
    error: string | null;
    text: string | null;
    at: string | null;
  };
};

/** A post's numbers on Facebook as of `measured_at`; a number is null when Facebook does not give it. */
export type PostNumbers = {
  views: number | null;
  shares: number | null;
  comments: number | null;
  reactions: number | null;
  /** Plays without replays, and the replays. */
  plays: number | null;
  replays: number | null;
  /** People who saw the reel, as Facebook estimates them. */
  reach: number | null;
  /** Follows of the Page the reel brought. */
  followers: number | null;
  /** Average watch per play, replays included (so it can pass the reel's length). */
  avg_watch_seconds: number | null;
  view_time_seconds: number | null;
  /** `avg_watch_seconds` over the posted MP4's length; null when the length is not known. */
  watch_ratio: number | null;
  /** Share of plays still watching at evenly spaced points of the reel, from 1 at the start. */
  retention: number[] | null;
  measured_at: string;
};

/** Where a scene starts and ends in the posted MP4, in seconds. */
export type SceneMark = { label: string; start: number; end: number };

/** `latest` is rewritten by every reading; `at_48h` is the first reading 48 hours after the post went live, kept as it
 * is. `pending`: "Cập nhật view" was pressed and the worker has not read it yet. */
export type PostMetrics = {
  latest: PostNumbers | null;
  at_48h: PostNumbers | null;
  error: string | null;
  pending: boolean;
  analysis: PostAnalysis;
  /** The posted MP4's length and scenes; null and empty for a post made before the app kept them. */
  length_seconds: number | null;
  scenes: SceneMark[];
};

/** The post's 48-hour views against its Page's median of the last 60 days; `times_median` and the flag stay empty
 * until the post has its 48-hour numbers and the Page has enough measured posts. */
export type PostAnalysis = {
  median_views: number | null;
  samples: number;
  times_median: number | null;
  share_rate: number | null;
};

/** One week of the KPI strip, Monday to Sunday in Vietnam time (`start` is the Monday). */
export type WeekKpis = {
  start: string;
  measured: number;
  median_views: number | null;
  share_goal_met: number;
  share_goal_rate: number | null;
};

export type PostKpis = {
  this_week: WeekKpis;
  last_week: WeekKpis;
  rules: { median_days: number; min_samples: number; share_goal: number };
  /** Some Page has enough measured posts for its median to mean something. */
  enough_data: boolean;
};

/** A post in the "Bài đăng" list; `busy`: its video has a job queued or running. */
/** Where a post not on Facebook yet stands (api routes_posts._attempt): its publish job is still to run, or failed
 * with `error`, and "Thử lại" sends `job_id` again. Null once the post is on Facebook, cancelled or deleted. */
export type PostAttempt =
  { state: "working"; job_id: null; error: null } | { state: "failed"; job_id: number; error: string | null };

export type PostRow = Post & {
  video_id: number;
  title: string;
  thumbnail_url: string | null;
  busy: boolean;
  attempt: PostAttempt | null;
};

export type JobRow = {
  id: number;
  /** null for a plan job, which belongs to a topic group. */
  video_id: number | null;
  knowledge_topic_id: number | null;
  video_title: string;
  /** "plan": "Tạo bằng AI" of a 30-day plan, which belongs to a topic group. */
  kind: JobInfo["kind"] | "plan";
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

/** A multipart form, with or without a file (the file goes only when given). */
export async function postForm<T>(path: string, fields: Record<string, string>, file?: File | null): Promise<T> {
  const form = new FormData();
  for (const [name, value] of Object.entries(fields)) {
    form.append(name, value);
  }
  if (file) {
    form.append("file", file);
  }
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

/** An ISO time as a `datetime-local` input's value, in Vietnam time whatever the browser's time zone. */
export function vietnamInputValue(iso: string): string {
  const part = Object.fromEntries(dateParts.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${part.year}-${part.month}-${part.day}T${part.hour}:${part.minute}`;
}

/** A `datetime-local` value read as Vietnam time (no daylight saving there), as an ISO time. */
export function fromVietnamInput(value: string): string {
  return new Date(`${value}:00+07:00`).toISOString();
}

export function formatLastLogin(iso: string | null): string {
  return iso ? formatDateTime(iso) : "Chưa đăng nhập";
}

export function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : String(err);
}

/** A video waiting in a Page's posting queue ("Hàng chờ"); the worker schedules the first one at the Page's next
 * free posting time. `error` says why it could not be scheduled the last time it was tried. */
export type QueueItem = {
  id: number;
  fanpage_id: number;
  fanpage: string;
  video: { id: number; title: string; thumbnail_url: string | null };
  auto_comment: boolean;
  added_by: string;
  added_at: string;
  tried_at: string | null;
  error: string | null;
};

export type QueuePage = {
  id: number;
  name: string;
  owner: { id: number; name: string } | null;
  mine: boolean;
  topic: { id: number; name: string } | null;
  /** "HH:MM" in Vietnam: the Page's own times, else its topic group's. */
  post_times: string[];
  own_times: boolean;
  healthy: boolean;
  check_error: string | null;
  /** Posting times in the next `fill_ahead_hours` that no post of the Page takes yet. */
  free_slots: string[];
  items: QueueItem[];
};

export type QueueOverview = {
  pages: QueuePage[];
  topics: { id: number; name: string }[];
  fill_ahead_hours: number;
};
