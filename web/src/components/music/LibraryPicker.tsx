"use client";

import EmptyState from "@/components/EmptyState";
import { Button, Flex, List, Modal, Typography } from "antd";
import { useState } from "react";
import type { MusicTrack } from "@/lib/api";
import TrackFilters from "./TrackFilters";
import TrackTags from "./TrackTags";
import { useTracks, type TrackFilters as Filters } from "./useTracks";

/** Picks a track from the team library; `onPick` copies it into the video. */
export default function LibraryPicker({
  open,
  busy,
  onClose,
  onPick,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onPick: (track: MusicTrack) => void;
}) {
  const [filters, setFilters] = useState<Filters>({ q: "" });
  const { tracks, loading } = useTracks(filters, open);

  return (
    <Modal title="Chọn nhạc từ thư viện" open={open} onCancel={onClose} footer={null} width={720} destroyOnHidden>
      <TrackFilters value={filters} onChange={setFilters} />
      <List<MusicTrack>
        style={{ marginTop: 16 }}
        loading={loading}
        dataSource={tracks}
        locale={{ emptyText: <EmptyState description={"Không có bài nào khớp. Thêm bài ở trang Thư viện nhạc."} /> }}
        renderItem={(track) => (
          <List.Item
            data-testid="library-track"
            actions={[
              <Button key="pick" type="primary" disabled={busy} onClick={() => onPick(track)}>
                Dùng bài này
              </Button>,
            ]}
          >
            <Flex vertical gap={6} style={{ width: "100%" }}>
              <Typography.Text strong>{track.name}</Typography.Text>
              <TrackTags track={track} />
              <audio src={track.url} controls preload="none" style={{ width: "100%" }} />
            </Flex>
          </List.Item>
        )}
      />
    </Modal>
  );
}
