"use client";

import { FacebookFilled, TikTokFilled } from "@ant-design/icons";
import { Flex, Tag, Tooltip, theme } from "antd";
import type { CommentLinks } from "@/lib/api";
import { LINK_STATES, worstLinks } from "@/lib/commentLinks";

/** A Facebook Page or TikTok account, and its owner when it is a teammate's (null: the member's own). `links`: whether
 * the Page's comments under the post hold a Shopee link, shown as a dot (none for TikTok). */
export type Place = { platform: "facebook" | "tiktok"; name: string; owner: string | null; links?: CommentLinks };

const PLATFORMS: Place["platform"][] = ["facebook", "tiktok"];

function Logo({ platform }: { platform: Place["platform"] }) {
  return platform === "tiktok" ? <TikTokFilled /> : <FacebookFilled />;
}

function line(place: Place): string {
  const whose = place.owner ? `${place.name} của ${place.owner}: hoa hồng về ${place.owner}` : `${place.name}, của bạn`;
  const links = place.links ? LINK_STATES[place.links].label : "";
  return links ? `${whose} (${links})` : whose;
}

/** Green when the Page's comment holds a link, yellow while it lacks one, grey when there is no comment or it is not
 * known; nothing for a TikTok post. */
function LinkDot({ links }: { links: CommentLinks | undefined }) {
  const { token } = theme.useToken();
  if (!links || links === "off") {
    return null;
  }
  const tone = LINK_STATES[links].tone;
  const color =
    tone === "success" ? token.colorSuccess : tone === "warning" ? token.colorWarning : token.colorTextQuaternary;
  return (
    <span
      data-testid="link-dot"
      data-links={links}
      aria-hidden
      style={{
        display: "inline-block",
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: color,
        marginInlineEnd: 5,
      }}
    />
  );
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
          <LinkDot links={place.links} />
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
        <Logo platform={platform} /> <LinkDot links={worstLinks(places.map((place) => place.links ?? "off"))} />
        {places[0].name} +{places.length - 1}
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
