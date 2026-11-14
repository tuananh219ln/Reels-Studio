"use client";
import CloneModal, { type CloneTarget } from "@/components/video/CloneModal";

import { COLORS } from "@/app/theme";
import { useMe } from "@/components/MeContext";
import { EditorContext } from "@/components/video/AutoSaveField";
import MoveGroupDrawer from "@/components/video/MoveGroupDrawer";
import PresenceAvatars, { editorNames } from "@/components/video/PresenceAvatars";
import PostToast from "@/components/video/PostToast";
import PublishTab, { type SideTab } from "@/components/video/PublishTab";
import { usePostRound, type PostOutcome } from "@/components/video/postRound";
import { QcChip } from "@/components/video/QcCard";
import { RenderButtons, RenderStatus, showFirstBlocking } from "@/components/video/RenderBar";
import SampleCard from "@/components/video/SampleCard";
import SceneCard from "@/components/video/SceneCard";
import type { PostBlockKey } from "@/components/video/PostContent";
import { VIDEO_MODES, isBackdrop } from "@/components/video/videoModes";
import VideoPreview from "@/components/video/VideoPreview";
import VideoProgress from "@/components/video/VideoProgress";
import { ContentTypeField, PostedPlatforms, VideoKindTags } from "@/components/VideoKind";
import VideoStatusTags from "@/components/VideoStatusTags";
import {
  ApiError,
  api,
  errorMessage,
  formatDateTime,
  type SceneData,
  type VideoDetail,
  type VideoMode,
} from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { usePresence } from "@/lib/presence";
import {
  ArrowLeftOutlined,
  CheckOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  FolderOutlined,
  MoreOutlined,
  PlusOutlined,
  SendOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Drawer,
  Dropdown,
  Flex,
  Grid,
  Radio,
  Result,
  Segmented,
  Spin,
  Tooltip,
  Typography,
} from "antd";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

// Job status and teammates' edits arrive by polling; 2.5 s keeps the page live without a socket while a job runs,
// someone edits or a teammate has it open. A video only looked at, alone and with nothing running, is read less often.
const REFRESH_MS = 2500;
const IDLE_REFRESH_MS = 10_000;
const JOB_NAMES = {
  script: "Viết kịch bản",
  clone: "Nhân bản",
  learn: "Học từ video mẫu",
  render: "Render",
  publish: "Đăng Facebook",
  unpublish: "Gỡ bài Facebook",
  check: "Kiểm tra bài Facebook",
  image: "Tạo ảnh AI",
  photos: "Tự tìm ảnh",
  voice: "Tạo giọng thật",
  revise: "AI sửa theo góp ý",
  motion: "Cảnh động",
  tiktok_publish: "Đăng TikTok",
  image_edit: "Sửa ảnh",
  image_marks: "Tìm chữ/logo trên ảnh",
} as const;

// The side panel's drawer width; below WIDE_FROM the panel is a drawer opened from the header, from it a column of
// 40% beside the scenes' 60% (docs/decisions/2026-11-14-video-editor-spec.md).
const SIDE_WIDTH = 440;
const WIDE_FROM = 1100;
// The phone's own header bar (AppShell), under which the page's header sticks.
const PHONE_HEADER = 60;

/** Whether the window is at least `width` px wide, following it as it is resized. */
function useWiderThan(width: number) {
  return useSyncExternalStore(
    (changed) => {
      const query = window.matchMedia(`(min-width: ${width}px)`);
      query.addEventListener("change", changed);
      return () => query.removeEventListener("change", changed);
    },
    () => window.matchMedia(`(min-width: ${width}px)`).matches,
    () => true,
  );
}

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { message, modal } = App.useApp();
  const { me } = useMe();
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Why the video could not be read (the api down, a 500), shown with "Thử lại" while there is nothing to show yet.
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // /videos/<id>?clone=tiktok|page: a suggestion on "Bài đăng" or a card on the list opens the clone drawer with its
  // request filled in. Read from useSearchParams, not window.location when the state starts: after a link inside the
  // app the address only changes once the page has rendered.
  const askedClone = useSearchParams().get("clone");
  const [cloning, setCloning] = useState<CloneTarget | null>(null);
  const [moving, setMoving] = useState(false);
  const [seenAsk, setSeenAsk] = useState<string | null>(null);
  if (askedClone !== seenAsk) {
    setSeenAsk(askedClone);
    if (askedClone === "tiktok" || askedClone === "page") setCloning(askedClone);
  }
  // Drop the request from the address, so a reload does not open the drawer again.
  useEffect(() => {
    if (askedClone !== null) router.replace(`/videos/${id}`);
  }, [askedClone, id, router]);
  // The side panel's tab: "Đăng bài", "Bình luận & Sản phẩm" or "Thiết lập".
  const [sideTab, setSideTab] = useState<SideTab>("post");
  // From 1100 px the side panel sits beside the scenes; narrower, it is a drawer, open or not.
  const sideBySide = useWiderThan(WIDE_FROM);
  const [sideOpen, setSideOpen] = useState(false);
  // How each platform of the last "Đăng lên N nền tảng" ended, shown in the note at the top right until closed.
  const [outcomes, setOutcomes] = useState<PostOutcome[] | null>(null);
  const screens = Grid.useBreakpoint();
  // A computer has no header bar of its own (AppShell's lg); a phone leaves out the header's summary line.
  const desktop = screens.lg ?? true;
  const phone = !(screens.sm ?? true);
  // The fixed header's height, so the side panel sticks just under it and fills the rest of the window.
  const header = useRef<HTMLDivElement>(null);
  const [headerHeight, setHeaderHeight] = useState(120);
  const loaded = video !== null;
  useEffect(() => {
    const element = header.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setHeaderHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, [loaded]);
  const pending = useRef(new Set<Promise<unknown>>());
  // "Xem" or "Chỉnh sửa", chosen when the page opens: a video already rendered or posted opens in "Xem", so a stray
  // click cannot change it; a draft opens in "Chỉnh sửa". Null until the video has loaded.
  const [editing, setEditing] = useState<boolean | null>(null);
  // The other members with this video open, and whether they are editing it (information only, nothing locks).
  const others = usePresence(id, editing);
  // Fields whose last save was refused; "Xong" waits until there are none.
  const failedSaves = useRef(new Set<string>());
  // Which scene cards are open, by scene id: one at a time (opening one closes the others), all of them only through
  // "Mở tất cả". When the page opens, the first scene that blocks the render opens, or on a draft the first scene.
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  // A content scene being dragged by its handle, and the scene it would drop on.
  const [dragged, setDragged] = useState<number | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  // "Xem trước" is open from this scene (0 is the title scene); null: closed.
  const [previewFrom, setPreviewFrom] = useState<number | null>(null);

  /** Every video the api sends goes through here, so new scenes get their open/closed state. */
  const receive = useCallback((next: VideoDetail) => {
    const draft = !next.mp4 && !next.publication;
    setVideo(next);
    setEditing((current) => current ?? draft);
    setExpanded((current) => {
      const scenes = [next.title_scene, ...next.scenes].filter((scene): scene is SceneData => scene !== null);
      const unseen = scenes.filter((scene) => !(scene.id in current));
      if (unseen.length === 0) {
        return current;
      }
      const first = Object.keys(current).length === 0;
      const opened = first
        ? (scenes.find((scene) => scene.blocking.length > 0) ?? (draft ? scenes[0] : undefined))
        : undefined;
      return {
        ...current,
        ...Object.fromEntries(unseen.map((scene) => [scene.id, scene === opened])),
      };
    });
  }, []);

  const load = useCallback(async () => {
    try {
      receive(await api<VideoDetail>(`/videos/${id}`));
      setLoadError(null);
      setFetchError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadError(err.message);
      } else {
        setFetchError(errorMessage(err));
      }
    }
  }, [id, receive]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(load, video?.active_job || editing || others.length > 0 ? REFRESH_MS : IDLE_REFRESH_MS);

  // A render seen running on this page says when it is done, wherever the member has scrolled to.
  // Only a new MP4 counts: a cancelled or failed render leaves the old one's time as it was.
  const watchedRender = useRef<{ renderedAt: string | null } | null>(null);
  const rendering = video?.active_job?.kind === "render";
  const idle = video !== null && !video.active_job;
  const renderedAt = video?.mp4?.rendered_at ?? null;
  useEffect(() => {
    if (rendering) {
      watchedRender.current ??= { renderedAt };
    } else if (idle && watchedRender.current) {
      if (renderedAt && renderedAt !== watchedRender.current.renderedAt) message.success("Đã render xong MP4");
      watchedRender.current = null;
    }
  }, [rendering, idle, renderedAt, message]);

  const reportFailed = useCallback((field: string, bad: boolean) => {
    if (bad) {
      failedSaves.current.add(field);
    } else {
      failedSaves.current.delete(field);
    }
  }, []);

  const editor = useMemo(
    () => ({
      locked: video?.locked ?? false,
      readOnly: editing === false,
      reportFailed,
      track: (save: Promise<unknown>) => {
        pending.current.add(save);
        save.finally(() => pending.current.delete(save)).catch(() => undefined);
      },
      flush: async () => {
        (document.activeElement as HTMLElement | null)?.blur();
        await Promise.allSettled([...pending.current]);
      },
      onSaved: receive,
    }),
    [video?.locked, editing, reportFailed, receive],
  );
  // The post texts are not part of the video itself: they stay editable in "Xem" too.
  const postEditor = useMemo(() => ({ ...editor, readOnly: false }), [editor]);
  const postRound = usePostRound(video, receive, setOutcomes);
  const closeOutcomes = useCallback(() => setOutcomes(null), []);

  /** Run an action that returns the video; refusals show the api's message. */
  async function act(action: () => Promise<VideoDetail>) {
    setBusy(true);
    try {
      receive(await action());
    } catch (err) {
      message.error(errorMessage(err));
      void load();
    } finally {
      setBusy(false);
    }
  }

  async function render() {
    // "Render" uses the saved data: leave the field being typed in and wait until it is saved.
    await editor.flush();
    await act(() => api<VideoDetail>(`/videos/${id}/render`, "POST"));
  }

  async function makeVoices() {
    // The job reads the saved voice texts: flush first, like "Render".
    await editor.flush();
    await act(() => api<VideoDetail>(`/videos/${id}/voices`, "POST"));
  }

  /** `provider`: the one picked from the button's arrow; the team's default otherwise. */
  async function generateImages(provider?: "cloudflare" | "gemini") {
    // The job reads the saved prompts: flush first, like "Render".
    await editor.flush();
    const query = provider ? `?provider=${provider}` : "";
    await act(() => api<VideoDetail>(`/videos/${id}/image${query}`, "POST"));
  }

  /** "Chỉnh sửa": unlocks the page; says so when someone else is editing, since the last field saved wins. */
  function startEditing() {
    const names = editorNames(others);
    if (names) {
      message.warning(
        `${names} đang chỉnh sửa video này. Nếu hai người sửa cùng một ô, ô lưu sau sẽ thay ô lưu trước.`,
      );
    }
    setEditing(true);
  }

  /** "Xong": saves the field being typed in, then locks the page again unless a save was refused. */
  async function finishEditing() {
    await editor.flush();
    if (failedSaves.current.size > 0) {
      message.warning("Còn ô chưa lưu được. Sửa ô báo lỗi rồi bấm “Xong” lại.");
      return;
    }
    setEditing(false);
  }

  /** Opens the first scene that has a red reason, alone, then scrolls to it. */
  function showBlocking() {
    const blocked = [video?.title_scene, ...(video?.scenes ?? [])].find(
      (scene): scene is SceneData => !!scene && scene.blocking.length > 0,
    );
    if (blocked) flushSync(() => openOnly(blocked.id));
    showFirstBlocking();
  }

  /** The scene ids in the page's order, the title scene first. */
  function sceneIds(): number[] {
    return [video?.title_scene, ...(video?.scenes ?? [])].filter((scene) => !!scene).map((scene) => scene!.id);
  }

  /** Opens one scene and closes the others: a card at a time, so the open one fits on the screen. */
  function openOnly(sceneId: number) {
    setExpanded(Object.fromEntries(sceneIds().map((other) => [other, other === sceneId])));
  }

  /** A scene's header: closes it when open, else opens it alone. */
  function toggle(sceneId: number) {
    if (expanded[sceneId]) {
      setExpanded((current) => ({ ...current, [sceneId]: false }));
    } else {
      openOnly(sceneId);
    }
  }

  /**
   * The keys of the scene list: ↑/↓ on a scene's header open the scene above or below; Ctrl+Enter (⌘+Enter) in a
   * scene saves the field being typed in and opens the next scene.
   */
  function sceneKeys(event: React.KeyboardEvent) {
    const target = event.target as HTMLElement;
    const card = target.closest<HTMLElement>("[data-scene-id]");
    if (!card) return;
    const ids = sceneIds();
    const index = ids.indexOf(Number(card.dataset.sceneId));
    const go = (next: number) => {
      if (next < 0 || next >= ids.length) return;
      event.preventDefault();
      // Leaving the field saves it, as a click elsewhere would.
      (document.activeElement as HTMLElement | null)?.blur();
      flushSync(() => openOnly(ids[next]));
      const header = document.querySelector<HTMLElement>(`[data-scene-id="${ids[next]}"] [data-testid="scene-toggle"]`);
      header?.focus();
      header?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      go(index + 1);
    } else if (target.closest('[data-testid="scene-toggle"]') && event.key === "ArrowDown") {
      go(index + 1);
    } else if (target.closest('[data-testid="scene-toggle"]') && event.key === "ArrowUp") {
      go(index - 1);
    }
  }

  /**
   * Shows the side panel (the drawer opens on a narrower screen) on the tab that holds a block and scrolls to it: the
   * status card or the caption on "Đăng bài", the comments or the products on "Bình luận & Sản phẩm".
   */
  function openSide(block: "ready" | PostBlockKey = "ready") {
    flushSync(() => {
      setSideTab(block === "comments" || block === "products" ? "engage" : "post");
      if (!sideBySide) setSideOpen(true);
    });
    const selector = block === "ready" ? '[data-testid="ready-card"]' : `[data-post-block="${block}"]`;
    // The drawer's panel is drawn while it opens: one frame later it can be scrolled to.
    requestAnimationFrame(() =>
      document.querySelector(`[data-side-panel] ${selector}`)?.scrollIntoView({ block: "start", behavior: "smooth" }),
    );
  }

  /** "Thử lại" on the note: the failed platform's job again; the note goes, the rows show how it went. */
  async function retryPost(outcome: PostOutcome) {
    setOutcomes(null);
    if (outcome.retryJobId !== null) {
      await act(() => api<VideoDetail>(`/jobs/${outcome.retryJobId}/retry`, "POST"));
    }
  }

  function setAllExpanded(open: boolean) {
    setExpanded(Object.fromEntries(sceneIds().map((sceneId) => [sceneId, open])));
  }

  /** "Thêm cảnh": the new scene opens, alone, ready to fill. */
  async function addScene() {
    setBusy(true);
    try {
      const next = await api<VideoDetail>(`/videos/${id}/scenes`, "POST");
      receive(next);
      const added = next.scenes[next.scenes.length - 1];
      if (added) {
        setExpanded(
          Object.fromEntries(
            [next.title_scene, ...next.scenes]
              .filter((scene) => !!scene)
              .map((scene) => [scene!.id, scene!.id === added.id]),
          ),
        );
      }
    } catch (err) {
      message.error(errorMessage(err));
      void load();
    } finally {
      setBusy(false);
    }
  }

  function remove() {
    modal.confirm({
      title: "Xóa video này?",
      content:
        "Xóa hẳn video, các cảnh, job và mọi file (ảnh, MP4, ảnh thu nhỏ). Không khôi phục được. " +
        "Bài đã đăng hoặc đã hẹn giờ trên Facebook vẫn còn.",
      okText: "Xóa",
      cancelText: "Huỷ",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api(`/videos/${id}`, "DELETE");
          message.success("Đã xóa video");
          router.push("/videos");
        } catch (err) {
          message.error(errorMessage(err));
        }
      },
    });
  }

  if (loadError) {
    return (
      <Result
        status="404"
        title={loadError}
        extra={
          <Link prefetch={false} href="/videos">
            Về danh sách video
          </Link>
        }
      />
    );
  }
  if (!video && fetchError) {
    return (
      <Result
        status="warning"
        title="Không tải được video"
        subTitle={fetchError}
        extra={
          <Button type="primary" onClick={() => void load()}>
            Thử lại
          </Button>
        }
      />
    );
  }
  if (!video) {
    return (
      <Flex justify="center" style={{ padding: 48 }}>
        <Spin size="large" />
      </Flex>
    );
  }

  const viewing = editing === false;
  const job = video.active_job;
  const failed = video.failed_job;
  const scenes = video.scenes;

  function move(index: number, step: -1 | 1) {
    const ids = scenes.map((scene) => scene.id);
    const target = index + step;
    if (target < 0 || target >= ids.length) {
      return;
    }
    [ids[index], ids[target]] = [ids[target], ids[index]];
    void act(() => api<VideoDetail>(`/videos/${id}/scene-order`, "PUT", { ids }));
  }

  /** A content scene dropped on another takes its place; the ones between shift by one. */
  function dropScene(movedId: number, targetId: number) {
    const ids = scenes.map((scene) => scene.id);
    const from = ids.indexOf(movedId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0 || from === to) return;
    ids.splice(from, 1);
    ids.splice(to, 0, movedId);
    void act(() => api<VideoDetail>(`/videos/${id}/scene-order`, "PUT", { ids }));
  }

  return (
    <EditorContext.Provider value={editor}>
      {/* Fixed at the top while the page scrolls: what the video is and how it stands, its main actions on the first
        row ("Xem trước" and "Render" always in reach), the progress line, QC and the render's state on the second. */}
      <div
        ref={header}
        data-testid="render-bar"
        data-compact={phone ? "true" : undefined}
        style={{
          position: "sticky",
          top: desktop ? 0 : PHONE_HEADER,
          zIndex: 9,
          margin: desktop ? "-32px -32px 12px" : "-20px -16px 12px",
          padding: desktop ? "12px 32px 10px" : "8px 16px",
          background: COLORS.layout,
          borderBottom: `1px solid ${COLORS.border}`,
        }}
      >
        <Flex wrap gap={8} justify="space-between" align="center">
          <Flex wrap align="center" gap="4px 10px" style={{ minWidth: 0, flex: "1 1 320px" }}>
            <Link prefetch={false} href="/videos" style={{ fontSize: 13, flex: "none" }}>
              <ArrowLeftOutlined /> Danh sách video
            </Link>
            {/* At least 300 px: on a phone it takes a row of its own rather than squeezing to a few letters. */}
            <Typography.Title
              level={4}
              ellipsis={{ tooltip: video.title || video.topic }}
              style={{ margin: 0, fontWeight: 600, flex: "1 1 300px", minWidth: 0 }}
              data-testid="video-title"
            >
              {video.title || video.topic}
            </Typography.Title>
            <Flex gap={10} align="center" wrap style={{ flex: "none" }}>
              <VideoStatusTags video={video} />
              {video.has_script && !viewing && (
                <Typography.Text type="secondary" style={{ fontSize: 13 }} data-testid="editing-tag">
                  Đang chỉnh sửa
                </Typography.Text>
              )}
              <PresenceAvatars others={others} />
            </Flex>
          </Flex>
          <Flex wrap gap={8} align="center">
            {video.has_script &&
              (viewing ? (
                <Button icon={<EditOutlined />} onClick={startEditing}>
                  Chỉnh sửa
                </Button>
              ) : (
                <Button type="primary" ghost icon={<CheckOutlined />} onClick={finishEditing}>
                  Xong
                </Button>
              ))}
            {/* In "Duyệt phân tích trước" the "Video mẫu" card writes, after saving the edited analysis. */}
            {!video.has_script && !job && !video.reference?.awaiting_review && (
              <Button
                type="primary"
                disabled={busy}
                onClick={() => act(() => api<VideoDetail>(`/videos/${id}/script`, "POST"))}
              >
                Viết kịch bản
              </Button>
            )}
            {/* The rarer actions sit under "⋯", "Xóa" last and apart. */}
            {(video.has_script || video.created_by_id === me.id || video.knowledge_topic_owner_id === me.id) && (
              <Dropdown
                trigger={["click"]}
                disabled={busy}
                menu={{
                  items: [
                    ...(video.has_script
                      ? [{ key: "clone", icon: <CopyOutlined />, label: "Nhân bản", onClick: () => setCloning("same") }]
                      : []),
                    ...(video.has_script && video.platform === "facebook"
                      ? [{ key: "tiktok", label: "Tạo bản TikTok", onClick: () => setCloning("tiktok") }]
                      : []),
                    // Only its maker moves or deletes a video (or its scenes); the api refuses anyone else.
                    ...(video.created_by_id === me.id
                      ? [
                          {
                            key: "group",
                            icon: <FolderOutlined />,
                            label: "Chuyển sang nhóm khác",
                            disabled: video.locked,
                            onClick: () => setMoving(true),
                          },
                          { type: "divider" as const },
                          {
                            key: "delete",
                            icon: <DeleteOutlined />,
                            label: "Xóa video",
                            danger: true,
                            disabled: video.locked,
                            onClick: remove,
                          },
                        ]
                      : []),
                    // The maker of the group a teammate's video sits in sends it back to a group of its maker.
                    ...(video.created_by_id !== me.id && video.knowledge_topic_owner_id === me.id
                      ? [
                          {
                            key: "group",
                            icon: <FolderOutlined />,
                            label: `Chuyển về nhóm của ${video.created_by}`,
                            disabled: video.locked,
                            onClick: () => setMoving(true),
                          },
                        ]
                      : []),
                  ],
                }}
              >
                <Button icon={<MoreOutlined />} aria-label="Thao tác khác với video" />
              </Dropdown>
            )}
            {video.has_script && (
              <RenderButtons
                video={video}
                busy={busy}
                onRender={render}
                onGenerateImages={generateImages}
                onPreview={async () => {
                  // The preview shows the saved scenes: the field being typed in is saved first.
                  await editor.flush();
                  setPreviewFrom(0);
                }}
              />
            )}
            {video.has_script && !sideBySide && (
              <Button icon={<SendOutlined />} onClick={() => openSide()} data-testid="open-side-panel">
                Đăng bài / Thiết lập
              </Button>
            )}
          </Flex>
        </Flex>
        <Flex wrap gap="4px 12px" align="center" justify="space-between" style={{ marginTop: 6 }}>
          <Flex wrap gap="4px 8px" align="center" style={{ minWidth: 0 }}>
            <VideoProgress video={video} onOpenTab={(tab) => openSide(tab === "post" ? "products" : "ready")} />
            {video.mp4?.qc && <QcChip qc={video.mp4.qc} />}
          </Flex>
          {video.has_script && (
            <RenderStatus
              video={video}
              busy={busy}
              compact={phone}
              onShowBlocking={showBlocking}
              jobName={job ? JOB_NAMES[job.kind] : undefined}
              onCancelJob={job ? () => act(() => api<VideoDetail>(`/jobs/${job.id}/cancel`, "POST")) : undefined}
            />
          )}
        </Flex>
      </div>
      {/* What the video is about and how it was made: read once, so it scrolls away under the header. */}
      <Flex wrap align="center" gap="4px 12px" style={{ marginBottom: 12 }} data-testid="video-kind-line">
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          Chủ đề {video.topic}
          {video.knowledge_topic ? `, nhóm ${video.knowledge_topic}` : ""}, tạo bởi {video.created_by} lúc{" "}
          <span data-testid="video-created-at">{formatDateTime(video.created_at)}</span>
        </Typography.Text>
        <ContentTypeField
          key={video.content_type}
          value={video.content_type}
          disabled={video.locked}
          onSave={(content_type) => act(() => api<VideoDetail>(`/videos/${id}`, "PATCH", { content_type }))}
        />
        {/* The type is in the field already; the tags say how the video was made. */}
        <VideoKindTags video={{ ...video, content_type: "" }} />
        <PostedPlatforms postedOn={video.posted_on ?? []} links={video.posted_links} />
      </Flex>
      {video.clone_of && (
        <Typography.Paragraph type="secondary" style={{ margin: "0 0 12px", fontSize: 13 }} data-testid="clone-of">
          Nhân bản từ “{video.clone_of.title}” — yêu cầu đổi: {video.clone_of.request}
        </Typography.Paragraph>
      )}
      {(video.variant_of || video.variants.length > 0) && (
        <Typography.Paragraph type="secondary" style={{ margin: "0 0 12px", fontSize: 13 }} data-testid="variants">
          {video.variant_of && (
            <>
              {/* The link goes to the Facebook video this TikTok version was made from; both share a title. */}
              Bản Facebook gốc:{" "}
              <Link prefetch={false} href={`/videos/${video.variant_of.id}`}>
                {video.variant_of.title}
              </Link>
            </>
          )}
          {video.variants.length > 0 && (
            <>
              Bản TikTok:{" "}
              {video.variants.map((variant, index) => (
                <span key={variant.id}>
                  {index > 0 && ", "}
                  <Link prefetch={false} href={`/videos/${variant.id}`}>
                    {variant.title}
                  </Link>
                </span>
              ))}
            </>
          )}
        </Typography.Paragraph>
      )}
      {video.plan_idea && (
        <Alert
          type="info"
          style={{ marginBottom: 12, padding: "6px 12px" }}
          data-testid="plan-idea-card"
          title={
            <>
              Theo kế hoạch 30 ngày, {video.plan_idea.day === null ? "Backlog" : `ngày ${video.plan_idea.day}`}
              {video.plan_idea.pain_group ? `, ${video.plan_idea.pain_group}` : ""}
            </>
          }
          description={
            <div style={{ fontSize: 13 }}>
              {video.plan_idea.pain && <div>Nỗi đau: {video.plan_idea.pain}</div>}
              {video.plan_idea.hook && <div>Hook: {video.plan_idea.hook}</div>}
            </div>
          }
        />
      )}

      {job && (
        <Alert
          type="info"
          showIcon
          icon={job.status === "running" ? <Spin size="small" /> : undefined}
          style={{ marginBottom: 16 }}
          data-testid="job-status"
          title={
            job.status === "queued"
              ? `${video.status_label}: ${JOB_NAMES[job.kind]}${job.scene_id !== null ? " (1 cảnh)" : ""}`
              : job.node_stage === "ready"
                ? `Đang chờ máy render: ${JOB_NAMES[job.kind]}`
                : job.node_stage === "taken"
                  ? `Máy render đang dựng: ${JOB_NAMES[job.kind]}…`
                  : job.kind === "render"
                    ? "Đang render video…"
                    : job.kind === "image"
                      ? "Đang tạo ảnh AI cho các cảnh thiếu…"
                      : job.kind === "publish"
                        ? "Đang đăng lên Facebook…"
                        : job.kind === "tiktok_publish"
                          ? "Đang gửi video lên TikTok…"
                          : job.kind === "unpublish"
                            ? "Đang gỡ bài trên Facebook…"
                            : job.kind === "check"
                              ? "Đang kiểm tra bài trên Facebook…"
                              : job.kind === "voice"
                                ? "ElevenLabs đang tạo giọng đọc cho các cảnh…"
                                : job.kind === "revise"
                                  ? "AI đang sửa video theo góp ý…"
                                  : job.kind === "motion"
                                    ? "HyperFrames đang dựng cảnh động…"
                                    : job.kind === "clone"
                                      ? "AI đang viết kịch bản nhân bản…"
                                      : job.kind === "learn"
                                        ? video.reference?.mode === "review" && !video.reference.analysis
                                          ? "AI đang xem và phân tích video mẫu…"
                                          : "AI đang xem video mẫu và viết kịch bản…"
                                        : "Đang viết kịch bản…"
          }
          description={
            job.node_stage === "ready"
              ? "Bật máy render (Cài đặt › Máy render) để dựng, hoặc Hủy. Video đang bị khóa cho tới khi job xong."
              : video.has_script
                ? "Video đang bị khóa cho tới khi job xong."
                : undefined
          }
          action={
            (job.status === "queued" || job.node_stage === "ready") && (
              <Button
                size="small"
                disabled={busy}
                onClick={() => act(() => api<VideoDetail>(`/jobs/${job.id}/cancel`, "POST"))}
              >
                Hủy
              </Button>
            )
          }
        />
      )}
      {failed && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          data-testid="job-error"
          title={`${failed.kind === "render" && video.mp4 ? "Render lại lỗi" : `${JOB_NAMES[failed.kind]} lỗi`}: ${failed.error ?? ""}`}
          description={
            failed.error_detail && (
              <Collapse
                ghost
                size="small"
                items={[
                  {
                    key: "detail",
                    label: "Chi tiết lỗi",
                    children: (
                      <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12 }}>{failed.error_detail}</pre>
                    ),
                  },
                ]}
              />
            )
          }
          action={
            <Button
              size="small"
              disabled={busy}
              onClick={() => act(() => api<VideoDetail>(`/jobs/${failed.id}/retry`, "POST"))}
            >
              Thử lại
            </Button>
          }
        />
      )}

      {video.reference && (
        <SampleCard
          sample={video.reference}
          videoId={video.id}
          hasScript={video.has_script}
          working={job !== null}
          onVideo={receive}
          onChanged={() => void load()}
        />
      )}
      {!video.has_script ? (
        !job &&
        !video.reference && (
          <Card>
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              Video chưa có kịch bản. Bấm “Viết kịch bản” để AI viết theo chủ đề.
            </Typography.Paragraph>
          </Card>
        )
      ) : (
        <SideLayout
          wide={sideBySide}
          top={headerHeight}
          open={sideOpen}
          onClose={() => setSideOpen(false)}
          panel={
            <PublishTab
              video={video}
              postEditor={postEditor}
              onApproved={load}
              tab={sideTab}
              onTab={setSideTab}
              posting={postRound.running}
              onPost={postRound.start}
              onRender={() => void render()}
            />
          }
        >
          {/* A light green outline while editing, so the member sees at a glance that the page can be changed. */}
          <Flex
            vertical
            gap={16}
            data-testid="editor-column"
            onKeyDown={sceneKeys}
            style={
              viewing ? undefined : { outline: `1px solid ${COLORS.primaryBorder}`, outlineOffset: 8, borderRadius: 12 }
            }
          >
            {video.video_blocking.map((reason) => (
              <Alert key={reason} type="error" showIcon title={reason} data-testid="video-blocking" />
            ))}
            {video.video_warnings
              .filter((warning) => warning.field === "total" || warning.field === "scenes")
              .map((warning) => (
                <Alert key={warning.message} type="warning" showIcon title={warning.message} />
              ))}
            {/* One row instead of two cards: the title picked from the script's options, and the video's kind. */}
            <Flex wrap align="center" gap="8px 16px" style={{ minHeight: 48 }} data-testid="scenes-toolbar">
              {video.title_scene && (
                <Flex align="center" gap={8} style={{ flex: "1 1 280px", minWidth: 0 }}>
                  <Typography.Text type="secondary" style={{ flex: "none", fontSize: 13 }}>
                    Tiêu đề
                  </Typography.Text>
                  <Dropdown
                    trigger={["click"]}
                    // Drawn while closed too, so the script's author can be read without opening it.
                    forceRender
                    disabled={video.title_options.length === 0}
                    popupRender={() => (
                      <Card size="small" style={{ maxWidth: 440 }} data-testid="title-options">
                        <Typography.Text type="secondary">Chọn 1 tiêu đề để chép vào chữ cảnh tiêu đề:</Typography.Text>
                        <Radio.Group
                          style={{ display: "flex", flexDirection: "column", gap: 6, margin: "8px 0 0" }}
                          value={video.title_options.indexOf(video.title_scene!.text)}
                          disabled={video.locked || viewing}
                          onChange={(event) => {
                            const text = video.title_options[event.target.value as number];
                            void act(() => api<VideoDetail>(`/scenes/${video.title_scene!.id}`, "PATCH", { text }));
                          }}
                          options={video.title_options.map((option, index) => ({ value: index, label: option }))}
                        />
                        {/* A script typed through MCP was written by the member's Claude: script_by names it. */}
                        {(video.script_by || video.hand_written) && (
                          <Typography.Text
                            type="secondary"
                            style={{ display: "block", marginTop: 10, fontSize: 12 }}
                            data-testid="script-by"
                          >
                            {video.script_by
                              ? `Kịch bản viết bởi ${video.script_by}`
                              : "Kịch bản tự viết, không qua AI"}
                          </Typography.Text>
                        )}
                      </Card>
                    )}
                  >
                    <Button style={{ flex: 1, minWidth: 0, justifyContent: "space-between" }} aria-label="Chọn tiêu đề">
                      <Typography.Text ellipsis style={{ minWidth: 0 }}>
                        {video.title_scene.text.replaceAll("*", "").replace(/\s+/g, " ").trim() || "(chưa có tiêu đề)"}
                      </Typography.Text>
                      <Typography.Text type="secondary" style={{ flex: "none", fontSize: 12 }}>
                        {video.title_options.length} gợi ý <DownOutlined style={{ fontSize: 10 }} />
                      </Typography.Text>
                    </Button>
                  </Dropdown>
                </Flex>
              )}
              <Flex align="center" gap={8} data-testid="video-mode">
                <Typography.Text type="secondary" style={{ flex: "none", fontSize: 13 }}>
                  Kiểu video
                </Typography.Text>
                <Tooltip title={VIDEO_MODES.find((item) => item.value === video.mode)?.hint}>
                  <Segmented
                    aria-label="Kiểu video"
                    value={video.mode}
                    disabled={video.locked || viewing}
                    options={VIDEO_MODES.map((item) => ({ value: item.value, label: item.label }))}
                    onChange={(value) =>
                      modal.confirm({
                        title: `Đổi sang “${VIDEO_MODES.find((item) => item.value === value)?.label}”?`,
                        content: "Ảnh, clip và ảnh món đã chọn vẫn được giữ, đổi lại lúc nào cũng được.",
                        okText: "Đổi",
                        cancelText: "Huỷ",
                        onOk: () => act(() => api<VideoDetail>(`/videos/${id}`, "PATCH", { mode: value as VideoMode })),
                      })
                    }
                  />
                </Tooltip>
              </Flex>
            </Flex>
            <Flex justify="space-between" align="center" gap={4}>
              <Typography.Text strong data-testid="scene-count">
                Cảnh ({scenes.length + (video.title_scene ? 1 : 0)})
              </Typography.Text>
              <Flex gap={4}>
                <Button size="small" type="link" onClick={() => setAllExpanded(true)}>
                  Mở tất cả
                </Button>
                <Button size="small" type="link" onClick={() => setAllExpanded(false)}>
                  Thu gọn tất cả
                </Button>
              </Flex>
            </Flex>
            {video.title_scene && (
              <SceneCard
                scene={video.title_scene}
                label="Cảnh tiêu đề"
                backdrop={isBackdrop(video)}
                generating={job?.kind === "image" && job.scene_id === video.title_scene.id}
                editing={job?.kind === "image_edit" && job.scene_id === video.title_scene.id}
                voiceEnabled={video.voice_enabled}
                onPreview={() => setPreviewFrom(0)}
                expanded={expanded[video.title_scene.id] ?? false}
                onToggle={() => toggle(video.title_scene!.id)}
              />
            )}
            {scenes.map((scene, index) => (
              <SceneCard
                key={scene.id}
                scene={scene}
                label={`Cảnh ${index + 1}`}
                backdrop={isBackdrop(video)}
                backdropScene={video.title_scene}
                generating={job?.kind === "image" && job.scene_id === scene.id}
                editing={job?.kind === "image_edit" && job.scene_id === scene.id}
                voiceEnabled={video.voice_enabled}
                onPreview={() => setPreviewFrom(index + (video.title_scene ? 1 : 0))}
                expanded={expanded[scene.id] ?? false}
                onToggle={() => toggle(scene.id)}
                onMove={(step) => move(index, step)}
                reorder={
                  viewing || video.locked
                    ? undefined
                    : {
                        dragging: dragged === scene.id,
                        over: dropTarget === scene.id && dragged !== scene.id,
                        onStart: () => setDragged(scene.id),
                        onOver: () => setDropTarget(scene.id),
                        onDrop: (movedId) => {
                          if (movedId) dropScene(movedId, scene.id);
                          setDragged(null);
                          setDropTarget(null);
                        },
                        onEnd: () => {
                          setDragged(null);
                          setDropTarget(null);
                        },
                      }
                }
                onDelete={
                  video.created_by_id === me.id
                    ? () => act(() => api<VideoDetail>(`/scenes/${scene.id}`, "DELETE"))
                    : undefined
                }
              />
            ))}
            <Button icon={<PlusOutlined />} disabled={video.locked || viewing || busy} onClick={() => void addScene()}>
              Thêm cảnh
            </Button>
          </Flex>
        </SideLayout>
      )}
      {previewFrom !== null && (
        <VideoPreview
          video={video}
          start={previewFrom}
          onClose={() => setPreviewFrom(null)}
          onMakeVoices={() => void makeVoices()}
        />
      )}
      <CloneModal videoId={video.id} target={cloning} onClose={() => setCloning(null)} />
      <MoveGroupDrawer video={video} open={moving} onClose={() => setMoving(false)} onMoved={receive} />
      {outcomes && (
        <PostToast
          outcomes={outcomes}
          right={desktop ? 32 : 16}
          onOpen={() => {
            setOutcomes(null);
            openSide();
          }}
          onRetry={(outcome) => void retryPost(outcome)}
          onClose={closeOutcomes}
        />
      )}
    </EditorContext.Provider>
  );
}

/**
 * The scenes and the side panel: from 1100 px side by side, 60% and 40%, the panel stuck under the header and
 * scrolling on its own while the scenes scroll with the page; on a narrower screen the scenes take the width and the
 * panel is a drawer.
 */
function SideLayout({
  wide,
  top,
  open,
  onClose,
  panel,
  children,
}: {
  wide: boolean;
  /** The fixed header's height. */
  top: number;
  open: boolean;
  onClose: () => void;
  panel: React.ReactNode;
  children: React.ReactNode;
}) {
  if (!wide) {
    return (
      <>
        {children}
        {/* Kept mounted while closed, so a field being typed in keeps its text. */}
        <Drawer
          open={open}
          onClose={onClose}
          placement="right"
          size={SIDE_WIDTH}
          forceRender
          title="Đăng bài / Thiết lập"
          styles={{ body: { paddingTop: 0 } }}
        >
          <div data-side-panel className="side-panel">
            {panel}
          </div>
        </Drawer>
      </>
    );
  }
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)",
        gap: 16,
        alignItems: "start",
      }}
    >
      <div style={{ minWidth: 0 }}>{children}</div>
      <div
        data-side-panel
        className="side-panel"
        style={{
          position: "sticky",
          top: top + 12,
          maxHeight: `calc(100vh - ${top + 22}px)`,
          overflowY: "auto",
          paddingRight: 4,
        }}
      >
        {panel}
      </div>
    </div>
  );
}
