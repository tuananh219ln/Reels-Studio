"use client";

import { FacebookFilled, TikTokFilled } from "@ant-design/icons";
import { Flex, Tag, Tooltip } from "antd";

/** A Facebook Page or TikTok account, and its owner when it is a teammate's (null: the member's own). */
export type Place = { platform: "facebook" | "tiktok"; name: string; owner: string | null };

function Logo({ platform }: { platform: Place["platform"] }) {
  return platform === "tiktok" ? <TikTokFilled /> : <FacebookFilled />;
}

function line(place: Place): string {
  const kind = place.platform === "tiktok" ? "TikTok" : "Page";
  return place.owner
    ? `${kind} ${place.name} · ${place.owner}: hoa hồng về ${place.owner}`
    : `${kind} ${place.name} · của bạn`;
}

/** Where something lives, kept short: one Page or account by name; two or more as the first one's logo and "+n",
 * every one of them named on hover. Gold when a teammate's is among them, as its commission is theirs. */
export default function PlacesChip({ places }: { places: Place[] }) {
  if (places.length === 0) {
    return null;
  }
  const theirs = places.some((place) => place.owner !== null);
  if (places.length === 1) {
    const [place] = places;
    return (
      <Tooltip title={line(place)}>
        <Tag
          bordered={false}
          color={theirs ? "gold" : undefined}
          icon={<Logo platform={place.platform} />}
          style={{ marginInlineEnd: 0, alignSelf: "flex-start" }}
          data-testid="video-post"
        >
          {place.name}
          {place.owner ? ` · ${place.owner}` : ""}
        </Tag>
      </Tooltip>
    );
  }
  return (
    <Tooltip
      title={
        <Flex vertical gap={2}>
          {places.map((place, index) => (
            <span key={index}>
              <Logo platform={place.platform} /> {line(place)}
            </span>
          ))}
        </Flex>
      }
    >
      <Tag
        bordered={false}
        color={theirs ? "gold" : undefined}
        style={{ marginInlineEnd: 0, alignSelf: "flex-start", cursor: "default" }}
        data-testid="video-places"
        aria-label={places.map(line).join("; ")}
      >
        <Logo platform={places[0].platform} /> +{places.length - 1}
      </Tag>
    </Tooltip>
  );
}
