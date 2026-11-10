"use client";

import { FacebookFilled, TikTokFilled } from "@ant-design/icons";
import { Flex, Tag, Tooltip } from "antd";

/** A Facebook Page or TikTok account, and its owner when it is a teammate's (null: the member's own). */
export type Place = { platform: "facebook" | "tiktok"; name: string; owner: string | null };

const PLATFORMS: Place["platform"][] = ["facebook", "tiktok"];

function Logo({ platform }: { platform: Place["platform"] }) {
  return platform === "tiktok" ? <TikTokFilled /> : <FacebookFilled />;
}

function line(place: Place): string {
  return place.owner ? `${place.name} của ${place.owner}: hoa hồng về ${place.owner}` : `${place.name}, của bạn`;
}

/** One platform's places: one by name; two or more as the first one's name and "+n", every one named on hover. Gold when a
 * teammate's is among them, as its commission is theirs. */
function PlatformChip({ platform, places }: { platform: Place["platform"]; places: Place[] }) {
  const theirs = places.some((place) => place.owner !== null);
  const kind = platform === "tiktok" ? "Tài khoản TikTok" : "Page Facebook";
  if (places.length === 1) {
    const [place] = places;
    return (
      <Tooltip title={`${kind}: ${line(place)}`}>
        <Tag
          bordered={false}
          color={theirs ? "gold" : undefined}
          icon={<Logo platform={platform} />}
          style={{ marginInlineEnd: 0 }}
          data-testid="video-post"
        >
          {place.name}
          {place.owner ? ` (${place.owner})` : ""}
        </Tag>
      </Tooltip>
    );
  }
  return (
    <Tooltip
      title={
        <Flex vertical gap={2}>
          <span>
            {places.length} {kind}
          </span>
          {places.map((place, index) => (
            <span key={index}>• {line(place)}</span>
          ))}
        </Flex>
      }
    >
      <Tag
        bordered={false}
        color={theirs ? "gold" : undefined}
        style={{ marginInlineEnd: 0, cursor: "default" }}
        data-testid="video-places"
        aria-label={`${places.length} ${kind}: ${places.map(line).join("; ")}`}
      >
        <Logo platform={platform} /> {places[0].name} +{places.length - 1}
      </Tag>
    </Tooltip>
  );
}

/** Where something lives, one chip per platform (Facebook, then TikTok), kept short. */
export default function PlacesChip({ places }: { places: Place[] }) {
  if (places.length === 0) {
    return null;
  }
  return (
    <Flex wrap gap={4}>
      {PLATFORMS.map((platform) => {
        const own = places.filter((place) => place.platform === platform);
        return own.length === 0 ? null : <PlatformChip key={platform} platform={platform} places={own} />;
      })}
    </Flex>
  );
}
