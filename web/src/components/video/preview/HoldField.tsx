"use client";

import { Flex, Segmented, Select, Typography } from "antd";

import { SCENE_HOLD_VALUES } from "@/lib/pcShopee";

/**
 * "Hiện chữ" of one scene of a PC Shopee video: how long its text stays before it fades out, over the video's
 * "Thời gian hiện chữ". Empty follows the video; every change is saved at once and undone with Ctrl+Z.
 */
export default function HoldField({
  value,
  videoValue,
  editable,
  onChange,
  zone,
  usualZone,
  onZone,
}: {
  zone: "top" | "bottom" | null;
  /** Where the scene's compact text or captions sit when nobody chose: the captions low, the text high. */
  usualZone: "top" | "bottom";
  onZone: (zone: "top" | "bottom" | null) => void;
  value: number | null;
  videoValue: number | null;
  editable: boolean;
  onChange: (value: number | null) => void;
}) {
  const follows =
    videoValue === null ? "theo video: suốt cảnh" : `theo video: ${videoValue.toString().replace(".", ",")} giây`;
  return (
    <Flex vertical gap={4} data-testid="scene-hold">
      <Typography.Text strong style={{ fontSize: 13 }}>
        Hiện chữ
      </Typography.Text>
      <Segmented
        size="small"
        aria-label="Vị trí chữ của cảnh"
        value={zone ?? usualZone}
        disabled={!editable}
        options={[
          { value: "top", label: "Trên" },
          { value: "bottom", label: "Dưới" },
        ]}
        onChange={(value) => onZone(value === usualZone ? null : (value as "top" | "bottom"))}
      />
      <Select
        size="small"
        allowClear
        aria-label="Hiện chữ của cảnh"
        placeholder={`Để trống: ${follows}`}
        value={value}
        disabled={!editable}
        options={SCENE_HOLD_VALUES.map((seconds) => ({
          value: seconds,
          label: `${seconds.toString().replace(".", ",")} giây`,
        }))}
        onChange={(next) => onChange(next ?? null)}
      />
    </Flex>
  );
}
