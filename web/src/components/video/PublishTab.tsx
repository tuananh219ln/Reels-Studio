"use client";

import {
  CaretRightFilled,
  CheckOutlined,
  ExportOutlined,
  FacebookFilled,
  InstagramOutlined,
  TikTokOutlined,
  YoutubeFilled,
} from "@ant-design/icons";
import { App, Button, Card, Collapse, Flex, Input, Radio, Select, Tabs, Typography } from "antd";
import Link from "next/link";
import { useEffect, useRef, useState, type ContextType } from "react";
import ApproveVideoButton from "@/components/actions/ApproveVideoButton";
import ListenVolume, { listenNow, setListen, useListen } from "@/components/ListenVolume";
import { useMe } from "@/components/MeContext";
import PostComment from "@/components/PostComment";
import {
  api,
  errorMessage,
  formatDateTime,
  formatDecimal,
  formatTime,
  fromVietnamInput,
  vietnamInputValue,
  type AffiliateAccount,
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
import { EditorContext, useEditor } from "./AutoSaveField";
import PostContent from "./PostContent";
import PostActions from "./PostActions";
import { PostRows, PublishButton } from "./PublishCard";
import type { PostStep } from "./postRound";
import SetupTab from "./SetupTab";

export type SideTab = "post" | "setup";

const ICONS: Record<PlatformKey, React.ReactNode> = {
  facebook: <FacebookFilled style={{ color: "#1877f2" }} />,
  tiktok: <TikTokOutlined />,
  youtube: <YoutubeFilled style={{ color: "#ff0000" }} />,
  instagram: <InstagramOutlined style={{ color: "#d6249f" }} />,
};

/**
 * The side panel beside the scenes: "Đăng bài" (where the video stands on posting, then the post's texts) and
 * "Thiết lập" (the video's own settings), the tabs kept at its top while it scrolls
 * (docs/decisions/2026-11-14-video-editor-spec.md).
 */
export default function PublishTab({
  video,
  postEditor,
  onApproved,
  tab,
  onTab,
  posting,
  onPost,
  onRender,
}: {
  video: VideoDetail;
  /** The post texts stay editable while the page is in "Xem". */
  postEditor: ContextType<typeof EditorContext>;
  onApproved: () => void;
  tab: SideTab;
  onTab: (tab: SideTab) => void;
  /** "Đăng lên N nền tảng" is going through its platforms. */
  posting: boolean;
  onPost: (steps: PostStep[]) => void;
  /** "Render lại", as the header's button. */
  onRender: () => void;
}) {
  return (
    <Tabs
      className="side-tabs"
      activeKey={tab}
      onChange={(key) => onTab(key as SideTab)}
      items={[
        {
          key: "post",
          label: "Đăng bài",
          forceRender: true,
          children: (
            <Flex vertical gap={12} data-testid="publish-tab">
              <ReadyCard video={video} onApproved={onApproved} posting={posting} onPost={onPost} onRender={onRender} />
              <EditorContext.Provider value={postEditor}>
                <PostContent video={video} />
              </EditorContext.Provider>
            </Flex>
          ),
        },
        // Kept mounted while hidden, so a file input or a field being typed in keeps working.
        { key: "setup", label: "Thiết lập", forceRender: true, children: <SetupTab video={video} /> },
      ]}
    />
  );
}

/**
 * The tab's first card, by where the video stands: no MP4 yet ("Sẵn sàng đăng?", how to get one); rendered and not out
 * ("Sẵn sàng đăng ✓": the MP4, the platforms to post to and "Đăng lên N nền tảng"); out ("● Đã đăng", one row per
 * platform, green out, red failed with "Thử lại").
 */
function ReadyCard({
  video,
  onApproved,
  posting,
  onPost,
  onRender,
}: {
  video: VideoDetail;
  onApproved: () => void;
  posting: boolean;
  onPost: (steps: PostStep[]) => void;
  onRender: () => void;
}) {
  const mp4 = video.mp4;
  const results = platformResults(video);
  const count = postCount(results);
  // A YouTube Shorts or Instagram tile opens "Tùy chọn khác" on its tab, where a post made by hand is recorded.
  const [request, setRequest] = useState<{ platform: PlatformKey; at: number } | null>(null);
  const more = <PublishButton video={video} label="Tùy chọn khác" type="link" request={request} />;
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

  if (!mp4) {
    return (
      <Card size="small" title="Sẵn sàng đăng?" data-testid="ready-card" data-state="no-mp4">
        <Flex vertical gap={8}>
          <Typography.Text type="secondary">
            Chưa có MP4. Bấm “Render” khi các cảnh đã đủ ảnh; MP4 và các nền tảng để đăng (Facebook, TikTok, YouTube
            Shorts, Instagram) sẽ hiện ở đây.
          </Typography.Text>
          {results.length > 0 && <ResultRows video={video} results={results} />}
          {history}
        </Flex>
      </Card>
    );
  }

  const posted = count.out > 0;
  const facts = <Mp4Facts video={video} onRender={onRender} />;
  if (posted) {
    // The newest Facebook post that is out or due carries the comment line.
    const open = video.publications.find((post) => post.status === "published" || post.status === "scheduled");
    return (
      <Card
        size="small"
        data-testid="ready-card"
        data-state="posted"
        title={
          <Flex align="center" gap={6}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a", flex: "none" }} />
            Đã đăng{count.last ? ` · ${formatDateTime(count.last)}` : ""}
          </Flex>
        }
      >
        <Flex gap={12} align="flex-start">
          <Mp4Frame key={mp4.url} url={mp4.url} seconds={mp4.seconds} />
          <Flex vertical gap={8} style={{ flex: 1, minWidth: 0 }}>
            <Typography.Text strong>
              Đã đăng lên {count.out}/{count.tried} nền tảng
            </Typography.Text>
            {facts}
            <ResultRows video={video} results={results} />
            {open && (
              <div data-testid="post-comment-state">
                <PostComment post={open} onChanged={() => undefined} readOnly />
              </div>
            )}
            <Flex gap={8} wrap align="center">
              <Platforms video={video} posting={posting} onPost={onPost} onManual={setRequest} compact />
            </Flex>
            {more}
          </Flex>
        </Flex>
        {history}
      </Card>
    );
  }

  return (
    <Card size="small" title="Sẵn sàng đăng ✓" data-testid="ready-card" data-state="ready">
      <Flex gap={12} align="flex-start">
        <Mp4Frame key={mp4.url} url={mp4.url} seconds={mp4.seconds} />
        <Flex vertical gap={8} style={{ flex: 1, minWidth: 0 }}>
          <Typography.Text strong>Video đã render xong</Typography.Text>
          {facts}
          {results.length > 0 && <ResultRows video={video} results={results} />}
        </Flex>
      </Flex>
      <div style={{ marginTop: 12 }}>
        <Platforms video={video} posting={posting} onPost={onPost} onManual={setRequest} />
      </div>
      <Flex justify="space-between" align="center" wrap style={{ marginTop: 4 }}>
        {more}
        {video.post_stage === "ready" && video.plan_idea?.suggested_post_at && (
          <ApproveVideoButton videoId={video.id} onDone={onApproved} />
        )}
      </Flex>
      {history}
    </Card>
  );
}

/** "MP4 · 1080×1920 · 12,0 giây · 3,4 MB", then "Tải MP4" and "Render lại" (the header's button). */
function Mp4Facts({ video, onRender }: { video: VideoDetail; onRender: () => void }) {
  const mp4 = video.mp4!;
  const bytes = useFileSize(mp4.url);
  const job = video.active_job !== null;
  return (
    <Flex vertical gap={2}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="render-time">
        {["MP4", "1080×1920", `${formatDecimal(mp4.seconds)} giây`, bytes ? megabytes(bytes) : null]
          .filter(Boolean)
          .join(" · ")}
      </Typography.Text>
      <Flex gap={12} wrap align="center" style={{ fontSize: 12 }}>
        <a href={mp4.download_url}>Tải MP4</a>
        <Button
          type="link"
          size="small"
          disabled={job || video.locked}
          onClick={onRender}
          style={{ padding: 0, height: "auto", fontSize: 12 }}
        >
          Render lại
        </Button>
      </Flex>
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

/** Each platform the video was tried on, one line: green out with its time and "Xem bài ↗", red with why and
 * "Thử lại", amber on its way or scheduled. A Facebook post keeps its actions (Kiểm tra, Hủy đăng/Xóa). */
function ResultRows({ video, results }: { video: VideoDetail; results: PlatformResult[] }) {
  return (
    <Flex vertical gap={6}>
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
  const status =
    result.state === "ok"
      ? `✓ ${result.at ? formatTime(result.at) : ""}`
      : result.state === "err"
        ? `✕ ${result.error ?? "Không đăng được"}`
        : result.post?.status === "scheduled" && result.at
          ? `Hẹn đăng lúc ${formatDateTime(result.at)}`
          : "Đang đăng…";

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

  return (
    <div
      className={`post-row post-row--${result.state}`}
      data-testid={`platform-row-${result.platform}`}
      data-status={result.post?.status ?? result.state}
    >
      {ICONS[result.platform]}
      <Typography.Text strong style={{ fontSize: 12, whiteSpace: "nowrap" }}>
        {PLATFORM_LABELS[result.platform]}
      </Typography.Text>
      <span
        className="post-row__status"
        data-testid={result.platform === "facebook" ? "publication-status" : undefined}
        style={{
          color: result.state === "err" ? "#c2410c" : undefined,
          overflow: "hidden",
          textOverflow: "ellipsis",
          minWidth: 0,
        }}
        title={status}
      >
        {status}
      </span>
      {result.state === "ok" && result.url && (
        <a href={result.url} target="_blank" rel="noreferrer" style={{ whiteSpace: "nowrap" }}>
          Xem bài <ExportOutlined style={{ fontSize: 10 }} />
        </a>
      )}
      {result.state === "err" && result.retryJobId !== null && (
        <Button size="small" loading={retrying} disabled={video.locked} onClick={() => void retry()}>
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

/**
 * The 2×2 grid of platforms, "Đăng ngay" or "Hẹn giờ", and "Đăng lên N nền tảng". Facebook and TikTok are posted by
 * the app (Facebook to the member's Page, TikTok as a draft to the member's connected account's inbox), one after the
 * other; YouTube Shorts and Instagram are posted by hand, so their tiles open "Tùy chọn khác" to record the link.
 * `compact`: a posted video offers only the button, for another platform.
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
  const results = platformResults(video);
  const tried = new Set(results.filter((result) => result.state !== "err").map((result) => result.platform));
  const [chosen, setChosen] = useState<PlatformKey[]>(() => (video.platform === "tiktok" ? ["tiktok"] : ["facebook"]));
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
      <Button size="small" onClick={() => setOpen(true)} disabled={video.locked}>
        Đăng thêm nền tảng
      </Button>
    );
  }

  const tile = (platform: PlatformKey) => {
    const auto = AUTO_PLATFORMS.includes(platform);
    const done = tried.has(platform);
    const selected = auto && chosen.includes(platform) && usable(platform) && !done;
    const note = done
      ? "Đã đăng"
      : !auto
        ? "Đăng tay, ghi link"
        : !usable(platform)
          ? "Không hẹn giờ được"
          : platform === "tiktok"
            ? "Nháp vào hộp thư"
            : null;
    return (
      <button
        key={platform}
        type="button"
        role={auto ? "checkbox" : undefined}
        aria-checked={auto ? selected : undefined}
        aria-label={PLATFORM_LABELS[platform]}
        data-testid={`platform-tile-${platform}`}
        disabled={(auto && (done || !usable(platform))) || video.locked}
        onClick={() => {
          if (!auto) {
            onManual({ platform, at: Date.now() });
            return;
          }
          setChosen((current) =>
            current.includes(platform) ? current.filter((item) => item !== platform) : [...current, platform],
          );
        }}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          minWidth: 0,
          height: 44,
          padding: "0 10px",
          borderRadius: 8,
          border: `1px solid ${selected ? "#c2410c" : "#e7e5e2"}`,
          background: selected ? "#fff1ea" : "#fff",
          cursor: "pointer",
          textAlign: "left",
          font: "inherit",
          opacity: auto && (done || !usable(platform)) ? 0.55 : 1,
        }}
      >
        <span style={{ fontSize: 18, flex: "none" }}>{ICONS[platform]}</span>
        <span style={{ minWidth: 0, flex: 1 }}>
          <span style={{ display: "block", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>
            {PLATFORM_LABELS[platform]}
          </span>
          {note && (
            <span style={{ display: "block", fontSize: 11, color: "#8a8784", whiteSpace: "nowrap" }}>{note}</span>
          )}
        </span>
        {selected && <CheckOutlined style={{ color: "#c2410c", flex: "none" }} />}
      </button>
    );
  };

  return (
    <Flex vertical gap={10} style={{ width: "100%" }} data-testid="post-platforms">
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 8 }}>
        {(["facebook", "tiktok", "youtube", "instagram"] as const).map(tile)}
      </div>
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
      <Flex align="center" gap={8} wrap>
        <Radio.Group
          aria-label="Lúc đăng"
          value={mode}
          onChange={(event) => setMode(event.target.value)}
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
            size="small"
            style={{ width: 200 }}
            onChange={(event) => setWhen(event.target.value)}
          />
        )}
      </Flex>
      {samePage && picked.includes("facebook") && (
        <Typography.Text type="danger" style={{ fontSize: 12 }}>
          Bản MP4 này đang có trên Fanpage đó. Hãy render bản mới hoặc xóa bài cũ.
        </Typography.Text>
      )}
      {video.mp4_outdated && (
        <Typography.Text type="warning" style={{ fontSize: 12 }}>
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
      >
        {posting ? "Đang đăng…" : `Đăng lên ${picked.length} nền tảng`}
      </Button>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Đăng bản MP4 mới nhất kèm caption và hashtag đã lưu; Facebook tự bình luận khi bài lên. Nhiều nền tảng thì đăng
        lần lượt, hãy để trang mở tới khi xong.
      </Typography.Text>
    </Flex>
  );
}

/** The MP4 small (120 × 213) with ▶ in its middle and its length in a corner; ▶ plays it with the browser's
 * controls, at the listener's volume (set under it: the player is too narrow for the browser's slider). */
function Mp4Frame({ url, seconds }: { url: string; seconds: number }) {
  const player = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const { level, muted } = useListen();
  useEffect(() => {
    if (!player.current) return;
    player.current.volume = level;
    player.current.muted = muted;
  }, [level, muted]);
  const length = `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
  return (
    <Flex vertical gap={4} style={{ flex: "none", width: 120 }}>
      <div style={{ position: "relative", width: 120, height: 213, borderRadius: 8, overflow: "hidden" }}>
        <video
          ref={player}
          src={url}
          controls={playing}
          preload="metadata"
          data-testid="mp4-player"
          // The browser's own mute button moves the shared level too, so every player stays in step.
          onVolumeChange={(event) => {
            const { volume, muted: silent } = event.currentTarget;
            const now = listenNow();
            if (Math.abs(volume - now.level) > 0.001 || silent !== now.muted) {
              setListen({ level: volume, muted: silent });
            }
          }}
          style={{ width: "100%", height: "100%", objectFit: "cover", background: "#000", display: "block" }}
        />
        {!playing && (
          <>
            <Button
              shape="circle"
              aria-label="Phát MP4"
              icon={<CaretRightFilled />}
              onClick={() => {
                setPlaying(true);
                void player.current?.play().catch(() => undefined);
              }}
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                transform: "translate(-50%, -50%)",
                background: "rgba(255,255,255,.94)",
                border: "none",
              }}
            />
            <span
              style={{
                position: "absolute",
                right: 6,
                bottom: 6,
                padding: "0 5px",
                borderRadius: 4,
                fontSize: 11,
                color: "#fff",
                background: "rgba(0,0,0,.6)",
              }}
            >
              {length}
            </span>
          </>
        )}
      </div>
      <ListenVolume width={80} />
    </Flex>
  );
}
