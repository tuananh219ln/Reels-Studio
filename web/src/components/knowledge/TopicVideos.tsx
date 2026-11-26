"use client";
import AutoApproveSwitch from "@/components/actions/AutoApproveSwitch";
import VideoActions from "@/components/actions/VideoActions";
import { usePolling } from "@/lib/polling";

import EmptyState from "@/components/EmptyState";
import VideoCard from "@/components/videoList/VideoCard";
import VideoTable from "@/components/videoList/VideoTable";
import { useVideoColumns } from "@/components/videoList/columns";
import { plain, videoDetails } from "@/components/videoList/format";
import { useVideoView, VideoSearch, ViewToggle } from "@/components/videoList/toolbar";
import VideoTitleCell from "@/components/VideoTitleCell";
import { api, errorMessage, type VideoRow } from "@/lib/api";
import { useUrlChoiceIf, useUrlPageIf } from "@/lib/urlState";
import { TOPIC_STATUS_FILTERS } from "@/lib/videoStatus";
import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { App, Button, Col, Flex, Row, Tabs, Tooltip } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

// Where the choice was kept before every list of videos shared one: "table" was the table, "list" the cards.
const LEGACY_VIEW = { key: "topic-videos-view", values: { table: "table", list: "cards" } } as const;

/** "Video" in Kho kiến thức: the videos of one topic group, newest first, each opening its video page. */
export default function TopicVideos({
  topicId,
  fanpageId,
  canCreate,
  visible = true,
}: {
  topicId: number;
  /** Only the videos posted on, or waiting in the queue of, this Page (a group several Pages post). */
  fanpageId?: number;
  canCreate: boolean;
  /** Whether its group is the one shown: only then are the search, filter and page in the address. */
  visible?: boolean;
}) {
  const { message } = App.useApp();
  const [rows, setRows] = useState<VideoRow[] | null>(null);
  const [search, setSearch] = useUrlChoiceIf<string>(visible, "q", "");
  const [status, setStatus] = useUrlChoiceIf<string | null>(visible, "status", null);
  const tablePage = useUrlPageIf(visible);
  const [view, setView] = useVideoView("table", LEGACY_VIEW);

  const listUrl = `/videos?knowledge_topic_id=${topicId}${fanpageId ? `&fanpage_id=${fanpageId}` : ""}`;
  const load = useCallback(
    async (quiet = false) => {
      try {
        setRows(await api<VideoRow[]>(listUrl));
      } catch (err) {
        if (!quiet) message.error(errorMessage(err));
      }
    },
    [listUrl, message],
  );
  useEffect(() => {
    let live = true;
    api<VideoRow[]>(listUrl).then(
      (found) => {
        if (live) setRows(found);
      },
      (err) => {
        if (live) {
          setRows([]);
          message.error(errorMessage(err));
        }
      },
    );
    return () => {
      live = false;
    };
  }, [listUrl, message]);
  // "Cập nhật view": the worker reads the numbers in its next rounds, so the list is read often for a while after.
  const [refreshing, setRefreshing] = useState(false);
  const [watching, setWatching] = useState(false);
  useEffect(() => {
    if (!watching) return;
    const timer = window.setTimeout(() => setWatching(false), 120_000);
    return () => window.clearTimeout(timer);
  }, [watching]);
  async function refreshViews() {
    setRefreshing(true);
    try {
      const { asked } = await api<{ asked: number }>(`/posts/refresh?knowledge_topic_id=${topicId}`, "POST");
      message.success(
        asked
          ? `Đã nhờ đọc lại view của ${asked} bài, số mới hiện sau ít phút`
          : "Không có bài nào cần đọc thêm (chưa có bài đã đăng, hoặc đang chờ đọc view rồi)",
      );
      setWatching(true);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setRefreshing(false);
    }
  }
  usePolling(
    async () => {
      if (visible) await load(true);
    },
    watching || rows?.some((row) => !["draft", "done", "failed"].includes(row.status)) ? 5000 : 60000,
  );

  // Every choice, with how many of the group's videos are in it, so a group of finished videos still shows the rest.
  const choice = TOPIC_STATUS_FILTERS.find((item) => item.value === status);
  const wanted = plain(search.trim());
  const shown = (rows ?? []).filter(
    (row) =>
      (!choice || choice.match(row)) &&
      (!wanted || plain(row.title).includes(wanted) || plain(row.topic).includes(wanted)),
  );

  const videoColumns = useVideoColumns({ storageKey: "topic-videos-columns", onChanged: () => void load(true) });

  return (
    <Flex vertical gap={12} data-testid="topic-videos">
      <Tabs
        size="small"
        activeKey={status ?? "all"}
        onChange={(key) => setStatus(key === "all" ? null : key)}
        tabBarStyle={{ marginBottom: 0 }}
        items={[
          { key: "all", label: `Tất cả (${(rows ?? []).length})` },
          ...TOPIC_STATUS_FILTERS.map(({ value, label, match }) => ({
            key: value,
            label: `${label} (${(rows ?? []).filter(match).length})`,
          })),
        ]}
      />
      <Flex wrap gap={8} justify="space-between">
        <Flex wrap gap={8}>
          <VideoSearch value={search} onChange={setSearch} label="Tìm video của nhóm" width={260} />
          <ViewToggle value={view} onChange={setView} />
          {view === "table" && videoColumns.picker}
        </Flex>
        <Flex wrap gap={16} align="center">
          <Tooltip title="Đọc lại view, share của các bài đã đăng trong nhóm từ Facebook">
            <Button icon={<ReloadOutlined />} loading={refreshing} onClick={refreshViews}>
              Cập nhật view
            </Button>
          </Tooltip>
          <AutoApproveSwitch />
          {canCreate && (
            <Link prefetch={false} href={`/videos?group=${topicId}`}>
              <Button type="primary" icon={<PlusOutlined />}>
                Tạo video
              </Button>
            </Link>
          )}
        </Flex>
      </Flex>
      {view === "cards" ? (
        <VideoCards rows={rows} shown={shown} onChanged={() => load(true)} />
      ) : (
        <VideoTable<VideoRow>
          size="small"
          rowKey="id"
          loading={rows === null}
          rows={shown}
          page={tablePage}
          empty={rows?.length ? "Không có video nào khớp" : "Nhóm này chưa có video nào"}
          actions={(row) => <VideoActions video={row} onChanged={() => load(true)} />}
          actionsWidth={88}
          columns={[
            {
              key: "title",
              title: "Video",
              width: 400,
              render: (_, row) => (
                <VideoTitleCell
                  id={row.id}
                  title={row.title || row.topic}
                  thumbnailUrl={row.thumbnail_url}
                  maxWidth={320}
                  sub={videoDetails(row)}
                />
              ),
            },
            ...videoColumns.columns,
          ]}
        />
      )}
    </Flex>
  );
}

/** "Thẻ": a card per video, the same card as the video list's. */
function VideoCards({
  rows,
  shown,
  onChanged,
}: {
  rows: VideoRow[] | null;
  shown: VideoRow[];
  onChanged: () => Promise<void>;
}) {
  if (rows !== null && shown.length === 0) {
    return <EmptyState description={rows.length ? "Không có video nào khớp" : "Nhóm này chưa có video nào"} />;
  }
  return (
    <Row gutter={[12, 12]} data-testid="topic-video-cards">
      {(rows === null ? [] : shown).map((row) => (
        <Col key={row.id} xs={24} xl={12} xxl={8} style={{ display: "flex" }}>
          <VideoCard row={row} showGroup={false} onChanged={onChanged} />
        </Col>
      ))}
    </Row>
  );
}
