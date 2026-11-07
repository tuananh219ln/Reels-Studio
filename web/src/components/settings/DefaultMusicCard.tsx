"use client";

import { Button, Card, Flex, Typography } from "antd";
import { useState } from "react";
import LibraryPicker from "@/components/music/LibraryPicker";
import type { VideoDefaults } from "@/lib/api";

/** "Nhạc nền mặc định" on Thiết lập mặc định: the library track every new video starts with (copied into it when the
 * video is created), or none. Edited with the rest of the page: kept in the draft until "Lưu". */
export default function DefaultMusicCard({
  values,
  onChange,
  disabled,
}: {
  values: VideoDefaults;
  onChange: (changes: Partial<VideoDefaults>) => void;
  disabled?: boolean;
}) {
  const [picking, setPicking] = useState(false);
  const track = values.music_track ?? null;
  // An id without its track: the track was deleted from the library after it was chosen.
  const gone = values.music_track_id !== null && track === null;

  return (
    <Card title="Nhạc nền mặc định" size="small" data-testid="default-music">
      <Flex vertical gap={10}>
        {track ? (
          <>
            <Typography.Text strong data-testid="default-music-name">
              {track.name}
            </Typography.Text>
            <audio src={track.url} controls preload="none" style={{ width: "100%" }} />
          </>
        ) : (
          <Typography.Text type={gone ? "warning" : "secondary"}>
            {gone
              ? "Bài nhạc mặc định đã bị xoá khỏi thư viện: video mới đang không có nhạc. Hãy chọn bài khác."
              : "Chưa chọn: video mới không có nhạc nền."}
          </Typography.Text>
        )}
        <Flex wrap gap={8}>
          <Button disabled={disabled} onClick={() => setPicking(true)}>
            {track ? "Đổi bài" : "Chọn từ thư viện"}
          </Button>
          {values.music_track_id !== null && (
            <Button disabled={disabled} onClick={() => onChange({ music_track_id: null, music_track: null })}>
              Bỏ nhạc mặc định
            </Button>
          )}
        </Flex>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Video tạo mới nhận một bản sao của bài này; sửa hay xoá bài trong thư viện sau đó không đổi video đã tạo.
          Video đã có giữ nhạc của nó, kể cả khi bấm “Lấy theo mặc định nhóm”.
        </Typography.Text>
      </Flex>
      <LibraryPicker
        open={picking}
        busy={false}
        onClose={() => setPicking(false)}
        onPick={(picked) => {
          onChange({ music_track_id: picked.id, music_track: { id: picked.id, name: picked.name, url: picked.url } });
          setPicking(false);
        }}
      />
    </Card>
  );
}
