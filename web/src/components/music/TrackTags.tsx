"use client";

import { Flex, Tag } from "antd";
import type { MusicTrack } from "@/lib/api";

export default function TrackTags({ track }: { track: MusicTrack }) {
  return (
    <Flex wrap gap={4}>
      {track.topics.map((topic) => (
        <Tag key={topic} color="blue">
          {topic}
        </Tag>
      ))}
      <Tag color="purple">{track.mood}</Tag>
    </Flex>
  );
}
