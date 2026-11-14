"use client";

import {
  CaretRightFilled,
  DownloadOutlined,
  ExportOutlined,
  InstagramOutlined,
  LoadingOutlined,
  TikTokOutlined,
} from "@ant-design/icons";
import { App, Button, Card, Collapse, Flex, Input, Modal, Radio, Select, Tooltip, Typography } from "antd";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import ApproveVideoButton from "@/components/actions/ApproveVideoButton";
import ListenVolume, { listenNow, setListen, useListen } from "@/components/ListenVolume";
import { useMe } from "@/components/MeContext";
import { COLORS } from "@/app/theme";
import {
  api,
  errorMessage,
  formatDateTime,
  formatDayTime,
  formatDecimal,
  formatTime,
  fromVietnamInput,
  vietnamInputValue,
  type AffiliateAccount,
  type Post,
  type VideoDetail,
} from "@/lib/api";
import { loadLastChoices, myPageOfGroup } from "@/lib/lastChoices";
import { myPages, pageOptions } from "@/lib/myPages";
import {
  AUTO_PLATFORMS,
  PLATFORM_LABELS,
  platformResults,
  postCount,
  type PlatformKey,
  type PlatformResult,
} from "@/lib/postResults";
import { useEditor } from "./AutoSaveField";
import PostActions from "./PostActions";
import { PostRows, PublishButton } from "./PublishCard";
import type { PostStep } from "./postRound";

/** The result colours of the publish panel spec; the brand's orange comes from the theme (COLORS). */
const SUCCESS = "#16A34A";
const DANGER = "#E5484D";

/**
 * Where the card stands: no MP4 yet; rendered and never tried ("ready"); a platform on its way ("publishing"); then,
 * from the platforms tried, all out ("published"), some out and some failed ("partial"), all failed ("failed"), or
 * only scheduled ("scheduled").
 */
type PanelState = "no-mp4" | "ready" | "publishing" | "published" | "partial" | "failed" | "scheduled";

function panelState(video: VideoDetail, results: PlatformResult[], posting: boolean): PanelState {
  if (!video.mp4) return "no-mp4";
  const scheduled = (result: PlatformResult) => result.state === "wait" && result.post?.status === "scheduled";
  if (posting || results.some((result) => result.state === "wait" && !scheduled(result))) return "publishing";
  if (results.length === 0) return "ready";
  const out = results.filter((result) => result.state === "ok").length;
  const failed = results.filter((result) => result.state === "err").length;
  if (failed === results.length) return "failed";
  if (failed > 0) return "partial";
  return out > 0 ? "published" : "scheduled";
}

const STATUS: Record<Exclude<PanelState, "no-mp4">, { text: string; color: string }> = {
  ready: { text: "Sẵn sàng đăng", color: SUCCESS },
  publishing: { text: "Đang đăng…", color: COLORS.primary },
  published: { text: "Đã đăng", color: SUCCESS },
  partial: { text: "Đã đăng một phần", color: COLORS.primary },
  failed: { text: "Đăng thất bại", color: DANGER },
  scheduled: { text: "Đã hẹn giờ", color: SUCCESS },
};

/** A platform's square badge, 20 × 20, its glyph white on its colour. */
function PlatformBadge({ platform }: { platform: PlatformKey }) {
  const glyph = {
    facebook: <span style={{ fontWeight: 700, fontSize: 13, fontFamily: "Arial, sans-serif" }}>f</span>,
    tiktok: <TikTokOutlined style={{ fontSize: 12 }} />,
    youtube: <CaretRightFilled style={{ fontSize: 12 }} />,
    instagram: <InstagramOutlined style={{ fontSize: 12 }} />,
  }[platform];
  return (
    <span className={`platform-badge platform-badge--${platform}`} aria-hidden>
      {glyph}
    </span>
  );
}

/** Opens the status card's posting drawer on a platform's tab, again each time `at` changes. */
export type DrawerRequest = { platform: PlatformKey; at: number };

/**
 * The "Đăng bài" tab's first card (docs/decisions/2026-11-14-publish-panel.md): a header with where the video stands,
 * then the MP4 small beside its facts and either the platforms to post to (rendered, not tried yet) or one row per
 * platform tried, with the pinned comment's state and "+ Đăng thêm". Without an MP4 it says how to get one.
 */
export default function StatusCard({
  video,
  onApproved,
  posting,
  onPost,
  onRender,
  drawerRequest = null,
}: {
  video: VideoDetail;
  onApproved: () => void;
  posting: boolean;
  onPost: (steps: PostStep[]) => void;
  onRender: () => void;
  /** "Tùy chọn đăng khác" in the "Thiết lập" tab: opens the drawer each time `at` changes. */
  drawerRequest?: DrawerRequest | null;
}) {
  const mp4 = video.mp4;
  const results = platformResults(video);
  const count = postCount(results);
  const state = panelState(video, results, posting);
  // A YouTube Shorts or Instagram row opens the posting drawer on its tab, where a post made by hand is recorded. The
  // drawer has no button on this card: "Tùy chọn đăng khác" is in the "Thiết lập" tab. The newer request opens it.
  const [rowRequest, setRequest] = useState<DrawerRequest | null>(null);
  const request = (rowRequest?.at ?? 0) >= (drawerRequest?.at ?? 0) ? rowRequest : drawerRequest;
  const rendering = video.active_job?.kind === "render";
  // The newest Facebook post that is out or due carries the pinned comment's state.
  const open = video.publications.find((post) => post.status === "published" || post.status === "scheduled");
  const scheduledAt = results.find((result) => result.post?.status === "scheduled")?.at ?? null;
  const when = state === "scheduled" ? scheduledAt : count.last;

  const header =
    state === "no-mp4" ? (
      "Sẵn sàng đăng?"
    ) : (
      <Flex align="center" gap={8} style={{ fontSize: 15, lineHeight: "20px" }} data-testid="publish-status">
        {state === "publishing" ? (
          <LoadingOutlined style={{ fontSize: 12, color: STATUS[state].color }} />
        ) : (
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: STATUS[state].color, flex: "none" }} />
        )}
        <span style={{ fontWeight: 600, color: STATUS[state].color }}>{STATUS[state].text}</span>
        {state !== "ready" && when && (
          <span style={{ fontWeight: 400, color: COLORS.textSecondary }}>· {formatDayTime(when)}</span>
        )}
      </Flex>
    );

  const history = video.publications.length > 0 && (
    <Collapse
      ghost
      size="small"
      data-testid="post-history"
      items={[
        {
          key: "history",
          forceRender: true,
          label: `Lịch sử bài Facebook (${video.publications.length})`,
          children: <PostRows video={{ ...video, tiktok_posts: [], manual_posts: [] }} />,
        },
      ]}
    />
  );

  // One card whatever the state: a post recorded in the drawer changes the card without closing the drawer.
  return (
    <Card
      size="small"
      title={header}
      className="publish-card"
      data-testid="ready-card"
      data-state={state}
      style={{ borderRadius: 12 }}
      styles={{ header: { padding: "12px 16px", minHeight: 0 }, body: { padding: 16 } }}
    >
      {!mp4 ? (
        <Flex vertical gap={8}>
          <Typography.Text type="secondary">
            Chưa có MP4. Bấm “Render” khi các cảnh đã đủ ảnh; MP4 và các nền tảng để đăng (Facebook, TikTok, YouTube
            Shorts, Instagram) sẽ hiện ở đây.
          </Typography.Text>
          {results.length > 0 && <ResultRows video={video} results={results} />}
        </Flex>
      ) : (
        <div className="publish-card__body">
          <VideoThumb key={mp4.url} url={mp4.url} seconds={mp4.seconds} />
          <Flex vertical gap={12} style={{ minWidth: 0 }}>
            <Flex vertical gap={2}>
              <Typography.Text strong style={{ fontSize: 15, lineHeight: "20px" }}>
                {count.tried === 0 ? "Video đã render xong" : `Đã đăng lên ${count.out}/${count.tried} nền tảng`}
              </Typography.Text>
              <VideoMeta video={video} short={state !== "ready"} onRender={onRender} />
            </Flex>
            {results.length > 0 && <ResultRows video={video} results={results} />}
            {state !== "ready" && open && <PinnedCommentStatus post={open} videoId={video.id} />}
            {rendering ? (
              <Typography.Text type="secondary" style={{ fontSize: 12.5 }} data-testid="publish-rendering">
                Đang render lại. Đăng được khi bản MP4 mới xong.
              </Typography.Text>
            ) : (
              state !== "publishing" && (
                <Platforms
                  key={state}
                  video={video}
                  posting={posting}
                  onPost={onPost}
                  onManual={setRequest}
                  compact={state !== "ready"}
                />
              )
            )}
          </Flex>
        </div>
      )}
      {mp4 && <PublishButton video={video} request={request} trigger={false} />}
      {video.post_stage === "ready" && video.plan_idea?.suggested_post_at && (
        <Flex justify="flex-end" style={{ marginTop: 8 }}>
          <ApproveVideoButton videoId={video.id} onDone={onApproved} />
        </Flex>
      )}
      {history}
    </Card>
  );
}

/**
 * "MP4 · 40 giây · 1080×1920 · 31,9 MB · Tải MP4 · Render lại"; once posted only "MP4 · 40 giây · Tải MP4".
 * "Render lại" asks first, then renders as the header's button does.
 */
function VideoMeta({ video, short, onRender }: { video: VideoDetail; short: boolean; onRender: () => void }) {
  const { modal } = App.useApp();
  const mp4 = video.mp4!;
  const bytes = useFileSize(mp4.url);
  const facts = short
    ? ["MP4", `${formatDecimal(mp4.seconds)} giây`]
    : ["MP4", `${formatDecimal(mp4.seconds)} giây`, "1080×1920", bytes ? megabytes(bytes) : null];
  const link = { padding: 0, height: "auto", fontSize: 13 } as const;

  function askRender() {
    modal.confirm({
      title: "Render lại video?",
      content: "Bản MP4 mới sẽ thay bản này. Trong lúc render, chưa đăng được.",
      okText: "Render lại",
      cancelText: "Huỷ",
      onOk: onRender,
    });
  }

  return (
    <Flex wrap align="center" gap="0 6px" style={{ fontSize: 13, lineHeight: "18px", color: COLORS.textSecondary }}>
      <span data-testid="render-time">{facts.filter(Boolean).join(" · ")}</span>
      <span aria-hidden>·</span>
      <a href={mp4.download_url} style={{ whiteSpace: "nowrap" }}>
        <DownloadOutlined aria-hidden /> Tải MP4
      </a>
      {!short && (
        <>
          <span aria-hidden>·</span>
          <Button
            type="link"
            size="small"
            disabled={video.active_job !== null || video.locked}
            onClick={askRender}
            style={link}
          >
            Render lại
          </Button>
        </>
      )}
    </Flex>
  );
}

function megabytes(bytes: number): string {
  return `${formatDecimal(bytes / 1024 / 1024)} MB`;
}

/** The MP4's size, read from a one-byte range of it (its Content-Range); null until known or when not given. */
function useFileSize(url: string): number | null {
  const [size, setSize] = useState<{ url: string; bytes: number | null } | null>(null);
  useEffect(() => {
    let live = true;
    fetch(url, { headers: { Range: "bytes=0-0" } })
      .then((response) => {
        const total = response.headers.get("content-range")?.split("/")[1];
        void response.body?.cancel();
        if (live) setSize({ url, bytes: total && /^\d+$/.test(total) ? Number(total) : null });
      })
      .catch(() => live && setSize({ url, bytes: null }));
    return () => {
      live = false;
    };
  }, [url]);
  return size?.url === url ? size.bytes : null;
}

/** Each platform the video was tried on, one row: green out with its time and "Xem bài ↗", red with why and
 * "Thử lại", a spinner on its way, its time when scheduled. A Facebook post keeps its actions (Kiểm tra, Hủy đăng). */
function ResultRows({ video, results }: { video: VideoDetail; results: PlatformResult[] }) {
  return (
    <Flex vertical gap={8}>
      {results.map((result) => (
        <ResultRow key={result.platform} video={video} result={result} />
      ))}
    </Flex>
  );
}

function ResultRow({ video, result }: { video: VideoDetail; result: PlatformResult }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [retrying, setRetrying] = useState(false);
  const label = PLATFORM_LABELS[result.platform];
  const draft =
    result.platform === "tiktok" &&
    result.state === "ok" &&
    video.tiktok_posts.find((post) => post.status === "published")?.mode === "draft";
  const scheduled = result.state === "wait" && result.post?.status === "scheduled" && result.at;

  async function retry() {
    setRetrying(true);
    try {
      editor.onSaved(await api<VideoDetail>(`/jobs/${result.retryJobId}/retry`, "POST"));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setRetrying(false);
    }
  }

  const status =
    result.state === "ok" ? (
      <>
        <span style={{ color: SUCCESS }}>✓</span>{" "}
        {draft ? (
          "Đã gửi nháp"
        ) : (
          <span style={{ color: COLORS.textSecondary }}>{result.at && formatTime(result.at)}</span>
        )}
      </>
    ) : result.state === "err" ? (
      <span style={{ color: DANGER }}>✕ {result.error ?? "Không đăng được"}</span>
    ) : scheduled ? (
      <span style={{ color: COLORS.textSecondary }}>Hẹn đăng lúc {formatDateTime(result.at!)}</span>
    ) : (
      <span style={{ color: COLORS.textSecondary }}>
        <LoadingOutlined style={{ marginRight: 6 }} />
        Đang đăng…
      </span>
    );

  return (
    <div
      className={`post-row post-row--${result.state}`}
      data-testid={`platform-row-${result.platform}`}
      data-status={result.post?.status ?? result.state}
    >
      <PlatformBadge platform={result.platform} />
      <span className="post-row__name">{label}</span>
      <span
        className="post-row__status"
        data-testid={result.platform === "facebook" ? "publication-status" : undefined}
        title={result.error ?? undefined}
      >
        {status}
      </span>
      {result.state === "ok" && result.url && (
        <a
          href={result.url}
          target="_blank"
          rel="noopener noreferrer"
          className="post-row__action"
          aria-label={`Xem bài trên ${label} (mở tab mới)`}
        >
          Xem bài <ExportOutlined style={{ fontSize: 11 }} />
        </a>
      )}
      {result.state === "err" && result.retryJobId !== null && (
        <Button
          type="link"
          size="small"
          loading={retrying}
          disabled={video.locked}
          onClick={() => void retry()}
          className="post-row__action"
        >
          Thử lại
        </Button>
      )}
      {result.post && result.state !== "err" && (
        // "Kiểm tra" and "Hủy đăng"/"Xóa" of the Facebook post.
        <PostActions post={result.post} disabled={video.locked} onDone={editor.onSaved} />
      )}
    </div>
  );
}

/** "Bình luận ghim: …": where the comment the Page writes under the reel stands. Facebook does not let an app pin it,
 * so once written it says to pin it by hand. */
function PinnedCommentStatus({ post, videoId }: { post: Post; videoId: number }) {
  const { message } = App.useApp();
  const editor = useEditor();
  const [asking, setAsking] = useState(false);
  const { state } = post.comment;
  if (state === "off") return null;
  const live = post.status === "published" && post.url !== null;

  async function retry() {
    setAsking(true);
    try {
      await api(`/posts/${post.id}/comment`, "POST");
      editor.onSaved(await api<VideoDetail>(`/videos/${videoId}`));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setAsking(false);
    }
  }

  return (
    <div style={{ fontSize: 13, lineHeight: "18px" }} data-testid="post-comment-state">
      <span style={{ color: COLORS.textSecondary }}>Bình luận ghim: </span>
      {state === "done" ? (
        <span style={{ color: SUCCESS }}>✓ đã đăng, nhớ ghim trên Facebook</span>
      ) : state === "failed" ? (
        <>
          <span style={{ color: DANGER }}>✕ không đăng được</span>
          {live && (
            <>
              {" · "}
              <Button
                type="link"
                size="small"
                loading={asking}
                onClick={() => void retry()}
                style={{ padding: 0, height: "auto", fontSize: 13 }}
              >
                Thử lại
              </Button>
            </>
          )}
        </>
      ) : (
        <span style={{ color: COLORS.textSecondary }}>đang chờ…</span>
      )}
    </div>
  );
}

/** The member's last pick of platforms, kept in this browser (try/catch: storage can be missing or refuse). */
function storedPlatforms(key: string): PlatformKey[] | null {
  try {
    const saved = window.localStorage.getItem(key);
    if (saved === null) return null;
    return saved.split(",").filter((item): item is PlatformKey => AUTO_PLATFORMS.includes(item as PlatformKey));
  } catch {
    return null;
  }
}

/**
 * The platforms as rows, "Đăng ngay" or "Hẹn giờ", and "Đăng lên N nền tảng". Facebook and TikTok are posted by the
 * app (Facebook to the member's Page, TikTok as a draft to the member's connected account's inbox), one after the
 * other; YouTube Shorts and Instagram are posted by hand, so their rows open the posting drawer to record the link.
 * `compact`: a video already tried offers only "+ Đăng thêm", for another platform.
 */
function Platforms({
  video,
  posting,
  onPost,
  onManual,
  compact = false,
}: {
  video: VideoDetail;
  posting: boolean;
  onPost: (steps: PostStep[]) => void;
  onManual: (request: { platform: PlatformKey; at: number }) => void;
  compact?: boolean;
}) {
  const { modal } = App.useApp();
  const { me } = useMe();
  const editor = useEditor();
  const hintId = useId();
  const results = platformResults(video);
  const tried = new Set(results.filter((result) => result.state !== "err").map((result) => result.platform));
  const storeKey = `reels:publish-platforms:${me.id}`;
  const [chosen, setChosenState] = useState<PlatformKey[]>(
    () => storedPlatforms(storeKey) ?? (video.platform === "tiktok" ? ["tiktok"] : ["facebook"]),
  );
  function setChosen(next: PlatformKey[]) {
    setChosenState(next);
    try {
      window.localStorage.setItem(storeKey, next.join(","));
    } catch {}
  }
  const planned = video.plan_idea?.suggested_post_at ?? null;
  const [mode, setMode] = useState<"now" | "later">(planned ? "later" : "now");
  const [when, setWhen] = useState(planned ? vietnamInputValue(planned) : "");
  const [open, setOpen] = useState(!compact);

  // Facebook: the member's own Page of the video's group, else the one they last posted to, else the only one.
  const mine = myPages(video.fanpages, me.id);
  const [pickedPage, setPickedPage] = useState<number | null>(null);
  const [lastPage, setLastPage] = useState<number | null>(null);
  useEffect(() => {
    void loadLastChoices().then((last) => setLastPage(last.fanpage_id));
  }, []);
  const fanpage =
    pickedPage ??
    myPageOfGroup(video, me.id) ??
    (mine.some((page) => page.id === lastPage) ? lastPage : null) ??
    (mine.length === 1 ? mine[0].id : null);
  const samePage = fanpage !== null && video.posted_fanpage_ids.includes(fanpage);

  // TikTok: the member's connected accounts; the Page's own TikTok account first.
  const [accounts, setAccounts] = useState<AffiliateAccount[] | null>(null);
  useEffect(() => {
    let live = true;
    api<AffiliateAccount[]>("/affiliate-accounts").then(
      (found) =>
        live &&
        setAccounts(
          found.filter(
            (account) =>
              account.platform === "tiktok" &&
              account.active &&
              account.tiktok_connection &&
              !account.tiktok_connection.needs_reconnect,
          ),
        ),
      () => live && setAccounts([]),
    );
    return () => {
      live = false;
    };
  }, []);
  const [pickedAccount, setPickedAccount] = useState<number | null>(null);
  const suggested = video.fanpages.find((page) => page.id === fanpage)?.tiktok_account_id ?? null;
  const account =
    pickedAccount ??
    (accounts?.some((item) => item.id === suggested) ? suggested : null) ??
    (accounts?.length === 1 ? accounts[0].id : null);

  // TikTok's API posts now or never: with "Hẹn giờ" only Facebook goes.
  const usable = (platform: PlatformKey) => !(platform === "tiktok" && mode === "later");
  const picked = chosen.filter((platform) => usable(platform) && !tried.has(platform));
  const missing =
    (picked.includes("facebook") && (fanpage === null || samePage)) ||
    (picked.includes("tiktok") && account === null) ||
    (mode === "later" && picked.includes("facebook") && !when);
  const blocked = video.mp4_outdated || video.locked || posting || picked.length === 0 || missing;

  async function post() {
    // The post uses the saved caption: leave the field being typed in and wait until it is saved.
    await editor.flush();
    const steps: PostStep[] = [];
    if (picked.includes("facebook") && fanpage !== null) {
      steps.push({
        platform: "facebook",
        body: {
          fanpage_id: fanpage,
          scheduled_at: mode === "later" ? fromVietnamInput(when) : null,
          auto_comment: true,
        },
      });
    }
    if (picked.includes("tiktok") && account !== null) {
      steps.push({ platform: "tiktok", body: { account_id: account, mode: "draft", privacy_level: null } });
    }
    onPost(steps);
  }

  function confirmAndPost() {
    // A red QC check does not stop posting, but the member says so first.
    if (video.mp4?.qc?.status !== "fail") {
      void post();
      return;
    }
    modal.confirm({
      title: "MP4 chưa đạt kiểm tra chất lượng",
      content: "Còn mục đỏ trong QC ở đầu trang. Nên sửa rồi render lại; vẫn đăng bản này?",
      okText: "Vẫn đăng",
      cancelText: "Huỷ",
      onOk: () => void post(),
    });
  }

  if (compact && !open) {
    return (
      <Button size="small" onClick={() => setOpen(true)} disabled={video.locked} style={{ alignSelf: "flex-start" }}>
        + Đăng thêm
      </Button>
    );
  }

  const option = (platform: PlatformKey) => {
    const label = PLATFORM_LABELS[platform];
    if (!AUTO_PLATFORMS.includes(platform)) {
      // Posted by hand: the row opens the posting drawer on its tab to record the post's link.
      return (
        <Tooltip key={platform} title="Đăng tay">
          <button
            type="button"
            className="platform-option platform-option--manual"
            data-testid={`platform-option-${platform}`}
            aria-label={`${label}, đăng tay, mở ô ghi link bài`}
            aria-describedby={`${hintId}-${platform}`}
            disabled={video.locked}
            onClick={() => onManual({ platform, at: Date.now() })}
          >
            <PlatformBadge platform={platform} />
            <span className="platform-option__name">{label}</span>
            <span id={`${hintId}-${platform}`} hidden>
              Đăng tay
            </span>
            <ExportOutlined className="platform-option__end" aria-hidden />
          </button>
        </Tooltip>
      );
    }
    const done = tried.has(platform);
    const checked = chosen.includes(platform) && usable(platform) && !done;
    const disabled = done || !usable(platform) || video.locked || posting;
    const hint = done
      ? "Đã đăng"
      : !usable(platform)
        ? "Không hẹn giờ được"
        : platform === "tiktok"
          ? "Nháp vào hộp thư"
          : null;
    // Only the badge and the name show; the hint is the row's tooltip and the checkbox's description.
    return (
      <Tooltip key={platform} title={hint}>
        <label
          className="platform-option"
          data-testid={`platform-option-${platform}`}
          data-checked={checked}
          data-disabled={disabled}
        >
          <PlatformBadge platform={platform} />
          <span className="platform-option__name">{label}</span>
          {hint && (
            <span id={`${hintId}-${platform}`} hidden>
              {hint}
            </span>
          )}
          <input
            type="checkbox"
            className="platform-option__check"
            aria-describedby={hint ? `${hintId}-${platform}` : undefined}
            checked={checked}
            disabled={disabled}
            onChange={() =>
              setChosen(chosen.includes(platform) ? chosen.filter((item) => item !== platform) : [...chosen, platform])
            }
          />
        </label>
      </Tooltip>
    );
  };

  const fromFacebook = picked.includes("facebook") && video.pinned_comment.trim() !== "";
  return (
    <Flex vertical gap={12} style={{ width: "100%" }} data-testid="post-platforms">
      <fieldset className="platform-list">
        <legend className="sr-only">Chọn nền tảng</legend>
        {(["facebook", "tiktok", "youtube", "instagram"] as const).map(option)}
      </fieldset>
      {picked.includes("facebook") && mine.length !== 1 && (
        <Flex align="center" gap={8}>
          <Typography.Text type="secondary" style={{ fontSize: 13, flex: "none" }}>
            Fanpage
          </Typography.Text>
          {mine.length === 0 ? (
            <Link prefetch={false} href="/fanpages" style={{ fontSize: 13 }}>
              Bạn chưa có Page nào, mở Quản lý Page
            </Link>
          ) : (
            <Select
              aria-label="Fanpage để đăng"
              placeholder="Chọn Fanpage"
              value={fanpage}
              onChange={setPickedPage}
              style={{ flex: 1, minWidth: 0 }}
              options={pageOptions(video.fanpages, me.id)}
            />
          )}
        </Flex>
      )}
      {picked.includes("tiktok") && accounts !== null && accounts.length !== 1 && (
        <Flex align="center" gap={8}>
          <Typography.Text type="secondary" style={{ fontSize: 13, flex: "none" }}>
            TikTok
          </Typography.Text>
          {accounts.length === 0 ? (
            <Link prefetch={false} href="/settings/affiliate-accounts" style={{ fontSize: 13 }}>
              Chưa kết nối tài khoản TikTok nào
            </Link>
          ) : (
            <Select
              aria-label="Tài khoản TikTok để đăng"
              placeholder="Chọn tài khoản"
              value={account}
              onChange={setPickedAccount}
              style={{ flex: 1, minWidth: 0 }}
              options={accounts.map((item) => ({
                value: item.id,
                label: `${item.name} (@${item.tiktok_connection?.username ?? ""})`,
              }))}
            />
          )}
        </Flex>
      )}
      <Flex vertical gap={8}>
        <Radio.Group
          aria-label="Lúc đăng"
          value={mode}
          disabled={posting}
          onChange={(event) => setMode(event.target.value)}
          style={{ display: "flex", gap: 24 }}
          options={[
            { value: "now", label: "Đăng ngay" },
            { value: "later", label: "Hẹn giờ" },
          ]}
        />
        {mode === "later" && (
          <Input
            type="datetime-local"
            aria-label="Giờ hẹn đăng"
            value={when}
            style={{ width: 220 }}
            onChange={(event) => setWhen(event.target.value)}
          />
        )}
      </Flex>
      {samePage && picked.includes("facebook") && (
        <Typography.Text type="danger" style={{ fontSize: 12.5 }}>
          Bản MP4 này đang có trên Fanpage đó. Hãy render bản mới hoặc xóa bài cũ.
        </Typography.Text>
      )}
      {video.mp4_outdated && (
        <Typography.Text type="warning" style={{ fontSize: 12.5 }}>
          MP4 cũ hơn bản sửa: hãy render lại trước khi đăng.
        </Typography.Text>
      )}
      <Button
        type="primary"
        block
        loading={posting}
        disabled={blocked}
        onClick={confirmAndPost}
        data-testid="post-to-platforms"
        style={{ height: 40, fontSize: 15, fontWeight: 600 }}
      >
        {posting
          ? "Đang đăng…"
          : picked.length === 0
            ? "Chọn nền tảng để đăng"
            : `${mode === "later" ? "Hẹn đăng" : "Đăng"} lên ${picked.length} nền tảng`}
      </Button>
      <div style={{ fontSize: 12.5, lineHeight: "18px", color: COLORS.textSecondary }}>
        <div>Đăng MP4 mới nhất kèm caption & hashtag đã lưu.</div>
        {fromFacebook && <div>Facebook tự bình luận khi bài lên.</div>}
        {picked.length > 1 && <div>Các nền tảng đăng lần lượt, hãy để trang mở tới khi xong.</div>}
      </div>
    </Flex>
  );
}

/**
 * The MP4 small (112 × 199, 96 × 171 in a narrow card) with ▶ in its middle and its length in a corner. ▶ opens it in
 * a window with the browser's controls, at the listener's volume (set under it).
 */
function VideoThumb({ url, seconds }: { url: string; seconds: number }) {
  const [open, setOpen] = useState(false);
  const length = `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
  return (
    <div className="publish-card__thumb">
      {/* The first frame stands for a poster: the render's own title, as viewers see it. */}
      <video src={url} preload="metadata" muted playsInline tabIndex={-1} aria-hidden />
      <button type="button" className="publish-card__play" aria-label="Phát MP4" onClick={() => setOpen(true)}>
        <CaretRightFilled />
      </button>
      <span className="publish-card__length">{length}</span>
      <Modal open={open} onCancel={() => setOpen(false)} footer={null} title="Xem MP4" width={380} destroyOnHidden>
        <Mp4Player url={url} />
      </Modal>
    </div>
  );
}

/** The MP4 with the browser's controls, playing at once, at the listener's volume. */
function Mp4Player({ url }: { url: string }) {
  const player = useRef<HTMLVideoElement>(null);
  const { level, muted } = useListen();
  useEffect(() => {
    if (!player.current) return;
    player.current.volume = level;
    player.current.muted = muted;
  }, [level, muted]);
  return (
    <Flex vertical gap={8} align="center">
      <video
        ref={player}
        src={url}
        controls
        autoPlay
        playsInline
        data-testid="mp4-player"
        // The browser's own mute button moves the shared level too, so every player stays in step.
        onVolumeChange={(event) => {
          const { volume, muted: silent } = event.currentTarget;
          const now = listenNow();
          if (Math.abs(volume - now.level) > 0.001 || silent !== now.muted) {
            setListen({ level: volume, muted: silent });
          }
        }}
        style={{ width: "100%", aspectRatio: "9 / 16", background: "#000", borderRadius: 10, display: "block" }}
      />
      <ListenVolume width={120} />
    </Flex>
  );
}
