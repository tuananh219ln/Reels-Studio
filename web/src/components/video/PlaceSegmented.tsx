"use client";

import { VerticalAlignBottomOutlined, VerticalAlignMiddleOutlined, VerticalAlignTopOutlined } from "@ant-design/icons";
import { Flex, Segmented, Typography } from "antd";
import { FRAME_HEIGHT } from "./preview/layers";

export type Place = "top" | "middle" | "bottom";

const ICONS = {
  top: <VerticalAlignTopOutlined />,
  middle: <VerticalAlignMiddleOutlined />,
  bottom: <VerticalAlignBottomOutlined />,
};

/**
 * One group of joined buttons, "Trên / Giữa / Dưới", for the place of the inset photo and of the text: short labels with
 * an icon so none is ever cut, the chosen one filled with the brand colour, arrow keys to change it. The label in front
 * says which of the two it is. `value` "" is a place in between (dragged), where none is chosen.
 */
export default function PlaceSegmented({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: Place | "";
  disabled?: boolean;
  onChange: (place: Place) => void;
}) {
  return (
    <Flex align="center" gap={8} className="place-segmented" style={{ minWidth: 0 }}>
      <Typography.Text strong style={{ fontSize: 12, flex: "none" }}>
        {label}
      </Typography.Text>
      <Segmented<Place | "">
        size="small"
        aria-label={label}
        value={value}
        disabled={disabled}
        options={(["top", "middle", "bottom"] as const).map((place) => ({
          value: place,
          label: (
            <span style={{ whiteSpace: "nowrap" }}>
              {ICONS[place]} {{ top: "Trên", middle: "Giữa", bottom: "Dưới" }[place]}
            </span>
          ),
        }))}
        onChange={(next) => next && onChange(next)}
      />
    </Flex>
  );
}

/** Where the scene's text box centre goes for each place; the box is kept inside the safe zone (textbox.place_box), so
 * "Trên" sits at the zone's top, "Dưới" is where the template puts it. */
export const TEXT_PLACES: Record<Place, [number, number]> = {
  top: [540, 0],
  middle: [540, FRAME_HEIGHT / 2],
  bottom: [540, FRAME_HEIGHT],
};

/** Which place a text box centre is: None placed means the template's (the bottom); a dragged one is none of them. */
export function textPlaceOf(placedAt: [number, number] | null): Place | "" {
  if (placedAt === null) return "bottom";
  return (Object.keys(TEXT_PLACES) as Place[]).find((place) => TEXT_PLACES[place][1] === placedAt[1]) ?? "";
}
