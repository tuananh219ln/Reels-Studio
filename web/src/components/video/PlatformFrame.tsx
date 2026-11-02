"use client";

import {
  BookOutlined,
  CameraOutlined,
  CustomerServiceOutlined,
  DislikeOutlined,
  EllipsisOutlined,
  HeartFilled,
  HomeFilled,
  LikeOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  PlusSquareOutlined,
  RetweetOutlined,
  SearchOutlined,
  SendOutlined,
  ShareAltOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";

export type Platform = "reels" | "tiktok" | "shorts";

export const PLATFORM_LABELS: Record<Platform, string> = {
  reels: "Reels",
  tiktok: "TikTok",
  shorts: "Shorts",
};

// Every place below is in the 1080×1920 frame, so the overlay sits where each app draws it on a phone.
const x = (px: number) => `${(px / 1080) * 100}%`;
const y = (px: number) => `${(px / 1920) * 100}%`;
// Sizes follow the stage's width (a container), so the overlay scales with the preview.
const u = (px: number) => `${(px / 1080) * 100}cqw`;

const shadow = "0 1px 3px rgba(0, 0, 0, 0.6)";

function At({
  left,
  top,
  right,
  bottom,
  children,
  style,
}: {
  left?: number;
  top?: number;
  right?: number;
  bottom?: number;
  children: ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        position: "absolute",
        left: left === undefined ? undefined : x(left),
        right: right === undefined ? undefined : x(right),
        top: top === undefined ? undefined : y(top),
        bottom: bottom === undefined ? undefined : y(bottom),
        color: "#fff",
        textShadow: shadow,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** One button of the right-hand column: an icon and, under it, a count or a word. */
function Action({ icon, label }: { icon: ReactNode; label?: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: u(6) }}>
      <span style={{ fontSize: u(76), lineHeight: 1, filter: `drop-shadow(${shadow})` }}>{icon}</span>
      {label && <span style={{ fontSize: u(27), fontWeight: 600 }}>{label}</span>}
    </div>
  );
}

function Column({ right, top, gap, children }: { right: number; top: number; gap: number; children: ReactNode }) {
  return (
    <At right={right} top={top}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: u(gap) }}>{children}</div>
    </At>
  );
}

function Avatar({ size, ring = false }: { size: number; ring?: boolean }) {
  return (
    <span
      style={{
        width: u(size),
        height: u(size),
        borderRadius: "50%",
        background: "linear-gradient(135deg, #8c8c8c, #434343)",
        border: ring ? `${u(4)} solid #fff` : undefined,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: u(size * 0.5),
        flex: "none",
      }}
    >
      <UserOutlined />
    </span>
  );
}

/** The apps' own bottom navigation bar: five icons on black. */
function NavBar({ icons, height }: { icons: ReactNode[]; height: number }) {
  return (
    <At
      left={0}
      right={0}
      bottom={0}
      style={{
        height: y(height),
        background: "#000",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-around",
        fontSize: u(60),
        textShadow: "none",
      }}
    >
      {icons.map((icon, index) => (
        <span key={index}>{icon}</span>
      ))}
    </At>
  );
}

function Caption({ text, width }: { text: string; width: number }) {
  return (
    <div
      style={{
        width: u(width),
        fontSize: u(30),
        overflow: "hidden",
        whiteSpace: "nowrap",
        textOverflow: "ellipsis",
      }}
    >
      {text}
    </div>
  );
}

/**
 * What a viewer's phone draws over the video in each app: the top bar, the right-hand buttons, the channel, caption
 * and sound at the bottom, and the navigation bar. Generic icons, laid out like each app, to judge what gets covered.
 */
export default function PlatformFrame({
  platform,
  channel,
  caption,
  music,
}: {
  platform: Platform;
  channel: string;
  caption: string;
  music: string;
}) {
  // The apps darken the bottom of the video so their white text reads on any picture.
  const fade = (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: "38%",
        background: "linear-gradient(to top, rgba(0,0,0,0.55), transparent)",
      }}
    />
  );
  // An @handle as the apps show it: no spaces, no Vietnamese marks.
  const handle = channel
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .replace(/[^A-Za-z0-9._]/g, "")
    .toLowerCase();

  if (platform === "tiktok") {
    return (
      <div data-testid="platform-frame" data-platform="tiktok" style={overlay}>
        {fade}
        <At left={40} top={80} style={{ fontSize: u(34), fontWeight: 700 }}>
          LIVE
        </At>
        <At left={0} right={0} top={74} style={{ display: "flex", justifyContent: "center", gap: u(40) }}>
          <span style={{ fontSize: u(36), opacity: 0.7, fontWeight: 600 }}>Đang theo dõi</span>
          <span style={{ fontSize: u(36), fontWeight: 700, borderBottom: `${u(5)} solid #fff`, paddingBottom: u(8) }}>
            Dành cho bạn
          </span>
        </At>
        <At right={40} top={70} style={{ fontSize: u(54) }}>
          <SearchOutlined />
        </At>
        <Column right={22} top={780} gap={26}>
          <span style={{ position: "relative", display: "inline-flex" }}>
            <Avatar size={100} ring />
            <span
              style={{
                position: "absolute",
                left: "50%",
                bottom: u(-18),
                transform: "translateX(-50%)",
                width: u(40),
                height: u(40),
                borderRadius: "50%",
                background: "#fe2c55",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: u(26),
              }}
            >
              <PlusOutlined />
            </span>
          </span>
          <Action icon={<HeartFilled />} label="12,4K" />
          <Action icon={<MessageOutlined />} label="318" />
          <Action icon={<BookOutlined />} label="1.024" />
          <Action icon={<ShareAltOutlined />} label="502" />
          <span
            style={{
              width: u(90),
              height: u(90),
              borderRadius: "50%",
              background: "radial-gradient(circle, #595959 30%, #141414 32%)",
              border: `${u(14)} solid #262626`,
            }}
          />
        </Column>
        <At left={36} bottom={150}>
          <div style={{ fontSize: u(36), fontWeight: 700, marginBottom: u(10) }}>@{handle || "tenkenh"}</div>
          <Caption text={caption} width={760} />
          <div style={{ fontSize: u(30), marginTop: u(10) }}>
            <CustomerServiceOutlined /> {music}
          </div>
        </At>
        <NavBar
          height={130}
          icons={[
            <HomeFilled key="home" />,
            <TeamOutlined key="friends" />,
            <span
              key="add"
              style={{
                padding: `${u(4)} ${u(24)}`,
                borderRadius: u(14),
                background: "#fff",
                color: "#000",
                fontSize: u(44),
                boxShadow: `${u(-6)} 0 0 #25f4ee, ${u(6)} 0 0 #fe2c55`,
              }}
            >
              <PlusOutlined />
            </span>,
            <MessageOutlined key="inbox" />,
            <UserOutlined key="me" />,
          ]}
        />
      </div>
    );
  }

  if (platform === "shorts") {
    return (
      <div data-testid="platform-frame" data-platform="shorts" style={overlay}>
        {fade}
        <At right={40} top={70} style={{ display: "flex", gap: u(50), fontSize: u(56) }}>
          <SearchOutlined />
          <EllipsisOutlined rotate={90} />
        </At>
        <Column right={24} top={960} gap={26}>
          <Action icon={<LikeOutlined />} label="12 N" />
          <Action icon={<DislikeOutlined />} label="Không thích" />
          <Action icon={<MessageOutlined />} label="318" />
          <Action icon={<ShareAltOutlined />} label="Chia sẻ" />
          <Action icon={<RetweetOutlined />} label="Phối lại" />
          <span style={{ width: u(80), height: u(80), borderRadius: u(14), background: "#595959" }} />
        </Column>
        <At left={36} bottom={190}>
          <div style={{ display: "flex", alignItems: "center", gap: u(18), marginBottom: u(14) }}>
            <Avatar size={64} />
            <span style={{ fontSize: u(32), fontWeight: 600 }}>@{handle || "tenkenh"}</span>
            <span
              style={{
                fontSize: u(28),
                fontWeight: 600,
                padding: `${u(8)} ${u(22)}`,
                borderRadius: u(40),
                background: "#fff",
                color: "#000",
                textShadow: "none",
              }}
            >
              Đăng ký
            </span>
          </div>
          <Caption text={caption} width={760} />
          <div style={{ fontSize: u(28), marginTop: u(10) }}>
            <CustomerServiceOutlined /> {music}
          </div>
        </At>
        {/* The red progress line sits right above the navigation bar. */}
        <At left={0} right={0} bottom={140} style={{ height: y(5), background: "rgba(255,255,255,0.35)" }}>
          <div style={{ width: "35%", height: "100%", background: "#f00" }} />
        </At>
        <NavBar
          height={140}
          icons={[
            <HomeFilled key="home" />,
            <PlayCircleOutlined key="shorts" />,
            <PlusSquareOutlined key="add" />,
            <TeamOutlined key="subs" />,
            <UserOutlined key="you" />,
          ]}
        />
      </div>
    );
  }

  return (
    <div data-testid="platform-frame" data-platform="reels" style={overlay}>
      {fade}
      <At left={40} top={70} style={{ fontSize: u(50), fontWeight: 700 }}>
        Reels
      </At>
      <At right={40} top={70} style={{ fontSize: u(56) }}>
        <CameraOutlined />
      </At>
      <Column right={30} top={1100} gap={30}>
        <Action icon={<HeartFilled />} label="12,4K" />
        <Action icon={<MessageOutlined />} label="318" />
        <Action icon={<SendOutlined rotate={-30} />} label="502" />
        <Action icon={<EllipsisOutlined />} />
        <span
          style={{
            width: u(70),
            height: u(70),
            borderRadius: u(12),
            border: `${u(4)} solid #fff`,
            background: "#595959",
          }}
        />
      </Column>
      <At left={36} bottom={170}>
        <div style={{ display: "flex", alignItems: "center", gap: u(18), marginBottom: u(16) }}>
          <Avatar size={70} />
          <span style={{ fontSize: u(32), fontWeight: 600 }}>{channel || "Tên kênh"}</span>
          <span
            style={{
              fontSize: u(28),
              fontWeight: 600,
              padding: `${u(6)} ${u(20)}`,
              borderRadius: u(14),
              border: `${u(3)} solid rgba(255,255,255,0.8)`,
            }}
          >
            Theo dõi
          </span>
        </div>
        <Caption text={caption} width={760} />
        <div style={{ fontSize: u(28), marginTop: u(12) }}>
          <CustomerServiceOutlined /> {music}
        </div>
      </At>
      <NavBar
        height={140}
        icons={[
          <HomeFilled key="home" />,
          <SearchOutlined key="search" />,
          <PlusSquareOutlined key="add" />,
          <PlayCircleOutlined key="reels" />,
          <UserOutlined key="me" />,
        ]}
      />
    </div>
  );
}

const overlay: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  pointerEvents: "none",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  lineHeight: 1.25,
};
