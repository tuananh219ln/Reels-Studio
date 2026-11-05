"use client";

import {
  ArrowLeftOutlined,
  CheckOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Flex,
  Grid,
  Input,
  Radio,
  Result,
  Row,
  Space,
  Spin,
  Tabs,
  Typography,
} from "antd";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import ListenVolume, { listenNow, setListen, useListen } from "@/components/ListenVolume";
import VideoStatusTags from "@/components/VideoStatusTags";
import { EditorContext } from "@/components/video/AutoSaveField";
import PostContent from "@/components/video/PostContent";
import PresenceAvatars, { editorNames } from "@/components/video/PresenceAvatars";
import PublishCard, { PublishButton } from "@/components/video/PublishCard";
import QueueButton from "@/components/video/QueueButton";
import TikTokCard from "@/components/video/TikTokCard";
import RenderBar, { showFirstBlocking } from "@/components/video/RenderBar";
import SampleCard from "@/components/video/SampleCard";
import SceneCard from "@/components/video/SceneCard";
import SetupTab from "@/components/video/SetupTab";
import VideoPreview from "@/components/video/VideoPreview";
import { ApiError, api, errorMessage, type SceneData, type VideoDetail } from "@/lib/api";
import { usePolling } from "@/lib/polling";
import { usePresence } from "@/lib/presence";
import { COLORS } from "@/app/theme";
import FormDrawer from "@/components/FormDrawer";

// Job status and teammates' edits arrive by polling; 2.5 s keeps the page live without a socket.
const REFRESH_MS = 2500;
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
} as const;

/** The side panel's tabs: the MP4 and posting, the video's own settings, and the post texts. */
type SideTab = "publish" | "setup" | "post";

// Side by side only on a computer, which has no header bar: just under the top, above the render bar.
const SIDE_PANEL_STYLE = {
  position: "sticky",
  top: 16,
  maxHeight: "calc(100vh - 16px - 96px)",
  overflowY: "auto",
  paddingRight: 4,
} as const;

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { message, modal } = App.useApp();
  const [video, setVideo] = useState<VideoDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // /videos/<id>?clone=tiktok|page: a suggestion on "Bài đăng" or a card on the list opens the clone drawer with its
  // request filled in. Read from useSearchParams, not window.location when the state starts: after a link inside the
  // app the address only changes once the page has rendered.
  const askedClone = useSearchParams().get("clone");
  const [cloning, setCloning] = useState<CloneTarget | null>(null);
  const [seenAsk, setSeenAsk] = useState<string | null>(null);
  if (askedClone !== seenAsk) {
    setSeenAsk(askedClone);
    if (askedClone === "tiktok" || askedClone === "page") setCloning(askedClone);
  }
  // Drop the request from the address, so a reload does not open the drawer again.
  useEffect(() => {
    if (askedClone !== null) router.replace(`/videos/${id}`);
  }, [askedClone, id, router]);
  // Until the member picks a tab, it follows the video: "Thiết lập" while there is no MP4, then "Xuất bản".
  const [sideTab, setSideTab] = useState<SideTab | null>(null);
  // The two columns sit side by side from xl up; only then does the side panel stick.
  const sideBySide = Grid.useBreakpoint().xl ?? false;
  const pending = useRef(new Set<Promise<unknown>>());
  // "Xem" or "Chỉnh sửa", chosen when the page opens: a video already rendered or posted opens in "Xem", so a stray
  // click cannot change it; a draft opens in "Chỉnh sửa". Null until the video has loaded.
  const [editing, setEditing] = useState<boolean | null>(null);
  // The other members with this video open, and whether they are editing it (information only, nothing locks).
  const others = usePresence(id, editing);
  // Fields whose last save was refused; "Xong" waits until there are none.
  const failedSaves = useRef(new Set<string>());
  // Which scene cards are open, by scene id. A scene seen for the first time opens when the video is a draft or
  // when the scene has something blocking the render; after that only the member opens or closes it.
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
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
      return {
        ...current,
        ...Object.fromEntries(unseen.map((scene) => [scene.id, draft || scene.blocking.length > 0])),
      };
    });
  }, []);

  const load = useCallback(async () => {
    try {
      receive(await api<VideoDetail>(`/videos/${id}`));
      setLoadError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadError(err.message);
      }
    }
  }, [id, receive]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);
  usePolling(load, REFRESH_MS);

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

  /** Opens every scene that has a red reason, then scrolls to the first one. */
  function showBlocking() {
    const blocked = [video?.title_scene, ...(video?.scenes ?? [])].filter(
      (scene): scene is SceneData => !!scene && scene.blocking.length > 0,
    );
    flushSync(() =>
      setExpanded((current) => ({ ...current, ...Object.fromEntries(blocked.map((scene) => [scene.id, true])) })),
    );
    showFirstBlocking();
  }

  function setAllExpanded(open: boolean) {
    const ids = [video?.title_scene, ...(video?.scenes ?? [])].filter((scene) => !!scene).map((scene) => scene!.id);
    setExpanded(Object.fromEntries(ids.map((sceneId) => [sceneId, open])));
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

  return (
    <EditorContext.Provider value={editor}>
      <Link prefetch={false} href="/videos" style={{ fontSize: 13 }}>
        <ArrowLeftOutlined /> Danh sách video
      </Link>
      <Flex wrap gap={12} justify="space-between" align="flex-start" style={{ margin: "6px 0 16px" }}>
        {/* Grows beside the actions, but never below 320 px: on a phone the actions wrap under the title. */}
        <div style={{ minWidth: 0, flex: "1 1 320px" }}>
          <Typography.Title level={3} style={{ margin: 0, fontWeight: 600 }} data-testid="video-title">
            {video.title || video.topic}
          </Typography.Title>
          {/* Status, the topic and who is here on one line, so the scenes start high on the screen. */}
          <Flex wrap align="center" gap={8} style={{ marginTop: 6 }}>
            <Flex gap={12} align="center" wrap>
              <VideoStatusTags video={video} />
              {video.has_script && !viewing && (
                <Typography.Text type="secondary" style={{ fontSize: 13 }} data-testid="editing-tag">
                  Đang chỉnh sửa
                </Typography.Text>
              )}
            </Flex>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              Chủ đề {video.topic}
              {video.knowledge_topic ? `, nhóm ${video.knowledge_topic}` : ""}, tạo bởi {video.created_by}
            </Typography.Text>
            <PresenceAvatars others={others} />
          </Flex>
          {video.clone_of && (
            <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 13 }} data-testid="clone-of">
              Nhân bản từ “{video.clone_of.title}” — yêu cầu đổi: {video.clone_of.request}
            </Typography.Paragraph>
          )}
          {(video.variant_of || video.variants.length > 0) && (
            <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 13 }} data-testid="variants">
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
              style={{ marginTop: 8, padding: "6px 12px" }}
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
        </div>
        <Space wrap>
          {video.has_script &&
            (viewing ? (
              <Button icon={<EditOutlined />} onClick={startEditing}>
                Chỉnh sửa
              </Button>
            ) : (
              <Button type="primary" icon={<CheckOutlined />} onClick={finishEditing}>
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
          {video.has_script && (
            <Button icon={<CopyOutlined />} disabled={busy} onClick={() => setCloning("same")}>
              Nhân bản
            </Button>
          )}
          {video.has_script && video.platform === "facebook" && (
            <Button disabled={busy} onClick={() => setCloning("tiktok")}>
              Tạo bản TikTok
            </Button>
          )}
          <Button danger icon={<DeleteOutlined />} disabled={video.locked || busy} onClick={remove}>
            Xóa
          </Button>
        </Space>
      </Flex>

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
              : job.kind === "render"
                ? "Đang render video…"
                : job.kind === "image"
                  ? "Đang tạo ảnh AI cho các cảnh thiếu…"
                  : job.kind === "publish"
                    ? "Đang đăng lên Facebook…"
                    : job.kind === "unpublish"
                      ? "Đang gỡ bài trên Facebook…"
                      : job.kind === "check"
                        ? "Đang kiểm tra bài trên Facebook…"
                        : job.kind === "voice"
                          ? "ElevenLabs đang tạo giọng đọc cho các cảnh…"
                          : job.kind === "revise"
                            ? "AI đang sửa video theo góp ý…"
                            : job.kind === "clone"
                              ? "AI đang viết kịch bản nhân bản…"
                              : job.kind === "learn"
                                ? video.reference?.mode === "review" && !video.reference.analysis
                                  ? "AI đang xem và phân tích video mẫu…"
                                  : "AI đang xem video mẫu và viết kịch bản…"
                                : "Đang viết kịch bản…"
          }
          description={video.has_script ? "Video đang bị khóa cho tới khi job xong." : undefined}
          action={
            job.status === "queued" && (
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
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={15}>
            {/* A light green outline while editing, so the member sees at a glance that the page can be changed. */}
            <Flex
              vertical
              gap={16}
              data-testid="editor-column"
              style={
                viewing
                  ? undefined
                  : { outline: `1px solid ${COLORS.primaryBorder}`, outlineOffset: 8, borderRadius: 12 }
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
              {video.title_scene && (
                <Card title="Tiêu đề" size="small">
                  <Typography.Text type="secondary">Chọn 1 tiêu đề để chép vào chữ cảnh tiêu đề:</Typography.Text>
                  <Radio.Group
                    style={{ display: "flex", flexDirection: "column", gap: 6, margin: "8px 0 0" }}
                    value={video.title_options.indexOf(video.title_scene.text)}
                    disabled={video.locked || viewing}
                    onChange={(event) => {
                      const text = video.title_options[event.target.value as number];
                      void act(() => api<VideoDetail>(`/scenes/${video.title_scene!.id}`, "PATCH", { text }));
                    }}
                    options={video.title_options.map((option, index) => ({ value: index, label: option }))}
                  />
                  {/* Under the options, not in the card's header, where on a phone it squeezed the title to "T…". */}
                  {video.hand_written && (
                    <Typography.Text
                      type="secondary"
                      style={{ display: "block", marginTop: 10, fontSize: 12 }}
                      data-testid="script-by"
                    >
                      Kịch bản tự viết, không qua AI
                    </Typography.Text>
                  )}
                  {video.script_by && (
                    <Typography.Text
                      type="secondary"
                      style={{ display: "block", marginTop: 10, fontSize: 12 }}
                      data-testid="script-by"
                    >
                      Kịch bản viết bởi {video.script_by}
                    </Typography.Text>
                  )}
                </Card>
              )}
              <Flex justify="flex-end" gap={4}>
                <Button size="small" type="link" onClick={() => setAllExpanded(true)}>
                  Mở tất cả
                </Button>
                <Button size="small" type="link" onClick={() => setAllExpanded(false)}>
                  Thu gọn tất cả
                </Button>
              </Flex>
              {video.title_scene && (
                <SceneCard
                  scene={video.title_scene}
                  label="Cảnh tiêu đề"
                  generating={job?.kind === "image" && job.scene_id === video.title_scene.id}
                  voiceEnabled={video.voice_enabled}
                  onPreview={() => setPreviewFrom(0)}
                  expanded={expanded[video.title_scene.id] ?? true}
                  onToggle={() => {
                    const titleId = video.title_scene!.id;
                    setExpanded((current) => ({ ...current, [titleId]: !(current[titleId] ?? true) }));
                  }}
                />
              )}
              {scenes.map((scene, index) => (
                <SceneCard
                  key={scene.id}
                  scene={scene}
                  label={`Cảnh ${index + 1}`}
                  generating={job?.kind === "image" && job.scene_id === scene.id}
                  voiceEnabled={video.voice_enabled}
                  onPreview={() => setPreviewFrom(index + (video.title_scene ? 1 : 0))}
                  expanded={expanded[scene.id] ?? true}
                  onToggle={() => setExpanded((current) => ({ ...current, [scene.id]: !(current[scene.id] ?? true) }))}
                  onMove={(step) => move(index, step)}
                  onDelete={() => act(() => api<VideoDetail>(`/scenes/${scene.id}`, "DELETE"))}
                />
              ))}
              <Button
                icon={<PlusOutlined />}
                disabled={video.locked || viewing || busy}
                onClick={() => act(() => api<VideoDetail>(`/videos/${id}/scenes`, "POST"))}
              >
                Thêm cảnh
              </Button>
            </Flex>
          </Col>
          <Col xs={24} xl={9}>
            {/* On a wide screen the side panel stays in view while the scenes scroll past it. */}
            <div style={sideBySide ? SIDE_PANEL_STYLE : undefined} data-side-panel>
              <Tabs
                activeKey={sideTab ?? (video.mp4 ? "publish" : "setup")}
                onChange={(key) => setSideTab(key as SideTab)}
                items={[
                  {
                    key: "publish",
                    label: "Xuất bản",
                    children: (
                      <Flex vertical gap={16}>
                        {video.mp4 ? (
                          <>
                            <Card title="MP4" size="small">
                              {/* The player small beside its facts, so posting stays in view under it. */}
                              <Flex gap={14} align="flex-start">
                                <Mp4Player key={video.mp4.url} url={video.mp4.url} />
                                <Flex vertical gap={10} style={{ minWidth: 0 }}>
                                  <Typography.Text type="secondary" data-testid="render-time">
                                    Dài {video.mp4.seconds.toFixed(1)} giây, render mất{" "}
                                    {video.mp4.render_seconds.toFixed(1)} giây
                                  </Typography.Text>
                                  <Button icon={<DownloadOutlined />} href={video.mp4.download_url}>
                                    Tải MP4
                                  </Button>
                                  {video.platform === "facebook" && <PublishButton video={video} />}
                                  {video.platform === "facebook" && <QueueButton video={video} />}
                                </Flex>
                              </Flex>
                            </Card>
                            {video.platform === "tiktok" ? <TikTokCard video={video} /> : <PublishCard video={video} />}
                          </>
                        ) : (
                          <Card size="small">
                            <Typography.Text type="secondary">
                              Chưa có MP4. Bấm “Render” ở thanh dưới cùng khi các cảnh đã đủ ảnh; MP4 và phần đăng
                              Facebook sẽ hiện ở đây.
                            </Typography.Text>
                          </Card>
                        )}
                      </Flex>
                    ),
                  },
                  {
                    key: "setup",
                    label: "Thiết lập",
                    children: <SetupTab video={video} />,
                  },
                  {
                    key: "post",
                    label: "Nội dung đăng",
                    children: (
                      <EditorContext.Provider value={postEditor}>
                        <PostContent video={video} />
                      </EditorContext.Provider>
                    ),
                  },
                ]}
              />
            </div>
          </Col>
        </Row>
      )}
      {video.has_script && (
        <RenderBar
          video={video}
          busy={busy}
          onRender={render}
          onGenerateImages={generateImages}
          onShowBlocking={showBlocking}
          jobName={job ? JOB_NAMES[job.kind] : undefined}
          onCancelJob={job ? () => act(() => api<VideoDetail>(`/jobs/${job.id}/cancel`, "POST")) : undefined}
          onPreview={async () => {
            // The preview shows the saved scenes: the field being typed in is saved first.
            await editor.flush();
            setPreviewFrom(0);
          }}
        />
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
    </EditorContext.Provider>
  );
}

/** What "Tạo bản TikTok" asks the clone for, filled in for the member to change: a different file and a different
 * hook from the Facebook reel, so neither platform sees a copy (docs/specs/multi-platform/plan.md). */
const TIKTOK_REQUEST =
  "Viết lại cho TikTok: mở đầu bằng một câu hỏi khơi bình luận, caption ngắn, ít hashtag, đổi 1–2 cảnh và ảnh khác bản Facebook";
/** What "Nhân bản cho Page khác" on "Bài đăng" asks for: a real variant, never the same file on a second Page. */
const PAGE_REQUEST = "Viết biến thể cho Page khác: đổi câu mở đầu, đổi 1–2 cảnh và ảnh, giữ chủ đề";

/** "same": "Nhân bản" with an empty request; "page": a variant for another Page; "tiktok": the TikTok version. */
type CloneTarget = "same" | "page" | "tiktok";

/** "Nhân bản": the team's LLM writes a new draft from this video as it is now, changed as the member asks.
 * "Tạo bản TikTok" is the same clone, made as the TikTok version of this video. */
function CloneModal({
  videoId,
  target,
  onClose,
}: {
  videoId: number;
  target: CloneTarget | null;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const router = useRouter();
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const open = target !== null;
  const tiktok = target === "tiktok";

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- a suggested request is prefilled each time it opens
    if (target === "tiktok" || target === "page") setRequest(target === "tiktok" ? TIKTOK_REQUEST : PAGE_REQUEST);
  }, [target]);

  async function submit() {
    setBusy(true);
    try {
      const draft = await api<VideoDetail>(`/videos/${videoId}/clone`, "POST", {
        request,
        ...(tiktok ? { platform: "tiktok" } : {}),
      });
      message.success(tiktok ? "Đã tạo bản TikTok" : "Đã tạo bản nháp nhân bản");
      onClose();
      router.push(`/videos/${draft.id}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={tiktok ? "Tạo bản TikTok" : "Nhân bản video"}
      open={open}
      onClose={onClose}
      onOk={submit}
      okText={tiktok ? "Tạo bản TikTok" : "Tạo bản nhân bản"}
      cancelText="Huỷ"
      okButtonProps={{ disabled: !request.trim() }}
      confirmLoading={busy}
      destroyOnHidden
      afterClose={() => setRequest("")}
    >
      <Typography.Paragraph type="secondary">
        AI giữ công thức của video này (đúng bản đang lưu) và viết một kịch bản mới theo yêu cầu đổi. Bản mới là một
        video nháp riêng, chưa có ảnh, có gợi ý nhạc mới, bản sao file MP3 và âm lượng; video này không bị khóa hay thay
        đổi.
      </Typography.Paragraph>
      <Typography.Text strong>Yêu cầu đổi</Typography.Text>
      <Input.TextArea
        aria-label="Yêu cầu đổi"
        value={request}
        placeholder="VD: đổi sang mốc 45 tuổi, tim mạch"
        autoSize={{ minRows: 2, maxRows: 5 }}
        maxLength={300}
        onChange={(event) => setRequest(event.target.value)}
      />
    </FormDrawer>
  );
}

/** The MP4 small beside its facts, with the listener's volume under it: at this width the browser's own controls
 * keep only a mute button. */
function Mp4Player({ url }: { url: string }) {
  const player = useRef<HTMLVideoElement>(null);
  const { level, muted } = useListen();
  useEffect(() => {
    if (!player.current) return;
    player.current.volume = level;
    player.current.muted = muted;
  }, [level, muted]);
  return (
    <Flex vertical gap={4} style={{ flex: "none", width: 150 }}>
      <video
        ref={player}
        src={url}
        controls
        preload="metadata"
        data-testid="mp4-player"
        // The browser's own mute button moves the shared level too, so every player stays in step.
        onVolumeChange={(event) => {
          const { volume, muted: silent } = event.currentTarget;
          const now = listenNow();
          if (Math.abs(volume - now.level) > 0.001 || silent !== now.muted) setListen({ level: volume, muted: silent });
        }}
        style={{ width: 150, aspectRatio: "9 / 16", background: "#000", borderRadius: 8 }}
      />
      <ListenVolume width={90} />
    </Flex>
  );
}
