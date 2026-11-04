"use client";

import { PlaySquareOutlined } from "@ant-design/icons";
import { Flex, Typography } from "antd";
import { useState } from "react";
import { COLORS } from "@/app/theme";

/** A video's title-scene thumbnail, or a tile with its name when there is none or it fails to load. With `width`
 * it is a small one for a table row; without, it fills a card's cover. */
export default function VideoThumbnail({
  name,
  url,
  width,
  plain = true,
}: {
  name: string;
  url: string | null;
  width?: number;
  /** A quiet grey tile when there is no thumbnail (the default); false keeps the brand-tinted tile. */
  plain?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const box = { width: width ?? "100%", aspectRatio: "9 / 16", borderRadius: width ? 6 : 0, flex: "none" } as const;
  if (url && !broken) {
    return (
      // A plain <img>: thumbnails come from the api behind the session cookie, which next/image's optimizer
      // would not send.
      // eslint-disable-next-line @next/next/no-img-element
      <img src={url} alt="" onError={() => setBroken(true)} style={{ ...box, objectFit: "cover" }} />
    );
  }
  return (
    <Flex
      align="center"
      justify="center"
      style={{
        ...box,
        background: plain ? COLORS.layout : COLORS.primaryBg,
        border: width ? `1px solid ${plain ? COLORS.border : COLORS.primaryBorder}` : undefined,
        padding: width ? 2 : 12,
        textAlign: "center",
      }}
    >
      {width ? (
        <PlaySquareOutlined
          style={{ color: plain ? COLORS.textSecondary : COLORS.primary, fontSize: plain ? 20 : 16 }}
        />
      ) : (
        <Typography.Text strong style={{ color: COLORS.primary }}>
          {name}
        </Typography.Text>
      )}
    </Flex>
  );
}
