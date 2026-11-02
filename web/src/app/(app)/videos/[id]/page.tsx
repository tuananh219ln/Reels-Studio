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
  Modal,
  Radio,
  Result,
  Row,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import VideoStatusTags from "@/components/VideoStatusTags";
import { EditorContext } from "@/components/video/AutoSaveField";
import PostContent from "@/components/video/PostContent";
import PublishCard from "@/components/video/PublishCard";
import RenderBar, { showFirstBlocking } from "@/components/video/RenderBar";
import SceneCard from "@/components/video/SceneCard";
import SetupTab from "@/components/video/SetupTab";
import VideoPreview from "@/components/video/VideoPreview";
import { ApiError, api, errorMessage, type SceneData, type VideoDetail } from "@/lib/api";

// Job status and teammates' edits arrive by polling; 2.5 s keeps the page live without a socket.
const REFRESH_MS = 2500;
const JOB_NAMES = {
  script: "Viết kịch bản",
  clone: "Nhân bản",
  render: "Render",
  publish: "Đăng Facebook",
  image: "Tạo ảnh AI",
} as const;

/** The side panel's tabs: the MP4 and posting, the video's own settings, and the post texts. */
type SideTab = "publish" | "setup" | "post";

// Below the sticky header (72 px) and above the render bar, so neither covers the panel.
const SIDE_PANEL_STYLE = {
  position: "sticky",
  top: 88,
  maxHeight: "calc(100vh - 88px - 96px)",
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
  const [cloning, setCloning] = useState(false);
  // Until the member picks a tab, it follows the video: "Thiết lập" while there is no MP4, then "Xuất bản".
  const [sideTab, setSideTab] = useState<SideTab | null>(null);
  // The two columns sit side by side from xl up; only then does the side panel stick.
  const sideBySide = Grid.useBreakpoint().xl ?? false;
  const pending = useRef(new Set<Promise<unknown>>());
  // "Xem" or "Chỉnh sửa", chosen when the page opens: a video already rendered or posted opens in "Xem", so a stray
  // click cannot change it; a draft opens in "Chỉnh sửa". Null until the video has loaded.
  const [editing, setEditing] = useState<boolean | null>(null);
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
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

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

  async function generateImages() {
    // The job reads the saved prompts: flush first, like "Render".
    await editor.flush();
    await act(() => api<VideoDetail>(`/videos/${id}/image`, "POST"));
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
    return <Result status="404" title={loadError} extra={<Link href="/videos">Về danh sách video</Link>} />;
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
      <Link href="/videos">
        <ArrowLeftOutlined /> Danh sách video
      </Link>
      <Flex wrap gap={12} justify="space-between" align="flex-start" style={{ margin: "12px 0 16px" }}>
        {/* Grows beside the actions, but never below 320 px: on a phone the actions wrap under the title. */}
        <div style={{ minWidth: 0, flex: "1 1 320px" }}>
          <Typography.Title level={2} style={{ margin: 0, fontWeight: 600 }} data-testid="video-title">
            {video.title || video.topic}
          </Typography.Title>
          <Typography.Text type="secondary">
            Chủ đề: {video.topic}
            {video.knowledge_topic ? ` · Nhóm: ${video.knowledge_topic}` : ""} · {video.created_by}
          </Typography.Text>
          {video.clone_of && (
            <Typography.Paragraph type="secondary" style={{ margin: 0 }} data-testid="clone-of">
              Nhân bản từ “{video.clone_of.title}” — yêu cầu đổi: {video.clone_of.request}
            </Typography.Paragraph>
          )}
          <div style={{ marginTop: 6 }}>
            <VideoStatusTags video={video} />
            {video.has_script && !viewing && (
              <Tag color="blue" data-testid="editing-tag">
                Đang chỉnh sửa
              </Tag>
            )}
          </div>
        </div>
        <Space wrap>
          {video.has_script &&
            (viewing ? (
              <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
                Chỉnh sửa
              </Button>
            ) : (
              <Button type="primary" icon={<CheckOutlined />} onClick={finishEditing}>
                Xong
              </Button>
            ))}
          {!video.has_script && !job && (
            <Button
              type="primary"
              disabled={busy}
              onClick={() => act(() => api<VideoDetail>(`/videos/${id}/script`, "POST"))}
            >
              Viết kịch bản
            </Button>
          )}
          {video.has_script && (
            <Button icon={<CopyOutlined />} disabled={busy} onClick={() => setCloning(true)}>
              Nhân bản
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
              ? `${video.status_label}: ${JOB_NAMES[job.kind]}`
              : job.kind === "render"
                ? "Đang render video…"
                : job.kind === "image"
                  ? "Đang tạo ảnh AI cho các cảnh thiếu…"
                  : job.kind === "publish"
                    ? "Đang đăng lên Facebook…"
                    : job.kind === "clone"
                      ? "AI đang viết kịch bản nhân bản…"
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

      {!video.has_script ? (
        !job && (
          <Card>
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              Video chưa có kịch bản. Bấm “Viết kịch bản” để AI viết theo chủ đề.
            </Typography.Paragraph>
          </Card>
        )
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} xl={15}>
            {/* A blue outline while editing, so the member sees at a glance that the page can be changed. */}
            <Flex
              vertical
              gap={16}
              data-testid="editor-column"
              style={viewing ? undefined : { outline: "2px solid #1677ff", outlineOffset: 6, borderRadius: 8 }}
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
                <Card
                  title="Tiêu đề"
                  size="small"
                  extra={
                    video.script_by && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }} data-testid="script-by">
                        Kịch bản viết bởi {video.script_by}
                      </Typography.Text>
                    )
                  }
                >
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
            <div style={sideBySide ? SIDE_PANEL_STYLE : undefined}>
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
                              <video
                                key={video.mp4.url}
                                src={video.mp4.url}
                                controls
                                preload="metadata"
                                data-testid="mp4-player"
                                style={{
                                  width: "100%",
                                  maxWidth: 320,
                                  aspectRatio: "9 / 16",
                                  background: "#000",
                                  borderRadius: 6,
                                }}
                              />
                              <Flex wrap gap={8} align="center" style={{ marginTop: 8 }}>
                                <Button icon={<DownloadOutlined />} href={video.mp4.download_url}>
                                  Tải MP4
                                </Button>
                                <Typography.Text type="secondary" data-testid="render-time">
                                  Dài {video.mp4.seconds.toFixed(1)} giây · render mất{" "}
                                  {video.mp4.render_seconds.toFixed(1)} giây
                                </Typography.Text>
                              </Flex>
                            </Card>
                            <PublishCard video={video} />
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
          onPreview={async () => {
            // The preview shows the saved scenes: the field being typed in is saved first.
            await editor.flush();
            setPreviewFrom(0);
          }}
        />
      )}
      {previewFrom !== null && <VideoPreview video={video} start={previewFrom} onClose={() => setPreviewFrom(null)} />}
      <CloneModal videoId={video.id} open={cloning} onClose={() => setCloning(false)} />
    </EditorContext.Provider>
  );
}

/** "Nhân bản": the team's LLM writes a new draft from this video as it is now, changed as the member asks. */
function CloneModal({ videoId, open, onClose }: { videoId: number; open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const router = useRouter();
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      const draft = await api<VideoDetail>(`/videos/${videoId}/clone`, "POST", { request });
      message.success("Đã tạo bản nháp nhân bản");
      onClose();
      router.push(`/videos/${draft.id}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Nhân bản video"
      open={open}
      onCancel={onClose}
      onOk={submit}
      okText="Tạo bản nhân bản"
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
    </Modal>
  );
}
