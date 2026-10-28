import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Series,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont } from "@remotion/google-fonts/BeVietnamPro";
import { ReelProps, Scene } from "./schema";

// ===== Thông số giao diện: sửa ở đây để đổi phong cách kênh =====
const THEME = {
  boxColor: "#FFD60A", // nền hộp chữ vàng
  boxText: "#111111",
  highlight: "#E10600", // màu từ khóa **...**
  badgeColor: "#E10600",
  titleSize: 84, // cỡ chữ hộp vàng
  benefitSize: 58, // cỡ chữ dòng lợi ích
};

const { fontFamily } = loadFont("normal", {
  weights: ["600", "800", "900"],
  subsets: ["vietnamese", "latin"],
});

// Nền tạm khi chưa có ảnh: mỗi cảnh một màu ấm
const PLACEHOLDER_BG = [
  "linear-gradient(160deg,#5b3a1a,#c98b3c)",
  "linear-gradient(160deg,#1f4d2b,#6fae5b)",
  "linear-gradient(160deg,#5a1f1f,#d0663f)",
  "linear-gradient(160deg,#2a3d5c,#7fa7c9)",
  "linear-gradient(160deg,#4a2a52,#b07cc0)",
  "linear-gradient(160deg,#3d3d1f,#b8a64a)",
];

// Chữ có **từ khóa** tô đỏ
const RichText: React.FC<{ text: string }> = ({ text }) => (
  <>
    {text.split(/(\*\*.+?\*\*)/).map((part, i) =>
      part.startsWith("**") ? (
        <span key={i} style={{ color: THEME.highlight }}>
          {part.slice(2, -2)}
        </span>
      ) : (
        <React.Fragment key={i}>{part}</React.Fragment>
      ),
    )}
  </>
);

// Ảnh nền zoom chậm (Ken Burns)
const Background: React.FC<{ image?: string; emoji?: string; index: number }> = ({
  image,
  emoji,
  index,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1.12]);

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {image ? (
        <Img
          src={staticFile(`photos/${image}`)}
          style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${scale})` }}
        />
      ) : (
        <AbsoluteFill
          style={{
            background: PLACEHOLDER_BG[index % PLACEHOLDER_BG.length],
            alignItems: "center",
            paddingTop: 260,
            transform: `scale(${scale})`,
          }}
        >
          <div style={{ fontSize: 420 }}>{emoji ?? "🍲"}</div>
        </AbsoluteFill>
      )}
      {/* lớp tối nhẹ để chữ luôn dễ đọc */}
      <AbsoluteFill
        style={{
          background: "linear-gradient(180deg,rgba(0,0,0,.35) 0%,rgba(0,0,0,0) 30%,rgba(0,0,0,0) 45%,rgba(0,0,0,.55) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};

// Hộp chữ vàng bật lên
const YellowBox: React.FC<{ children: React.ReactNode; size?: number }> = ({
  children,
  size = THEME.titleSize,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12, stiffness: 160 } });

  return (
    <div
      style={{
        background: THEME.boxColor,
        color: THEME.boxText,
        fontSize: size,
        fontWeight: 900,
        lineHeight: 1.18,
        textTransform: "uppercase",
        textAlign: "center",
        padding: "30px 44px",
        borderRadius: 22,
        maxWidth: 960,
        boxShadow: "0 12px 40px rgba(0,0,0,.45)",
        transform: `scale(${0.6 + 0.4 * pop})`,
        opacity: Math.min(1, pop * 1.5),
      }}
    >
      {children}
    </div>
  );
};

// Chữ trắng viền đen (dòng lợi ích)
const OutlinedText: React.FC<{ text: string; delay: number }> = ({ text, delay }) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [delay, delay + 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const stroke = "#000";
  const shadow = [-4, 0, 4]
    .flatMap((x) => [-4, 0, 4].map((y) => `${x}px ${y}px 0 ${stroke}`))
    .join(",");

  return (
    <div
      style={{
        color: "#fff",
        fontSize: THEME.benefitSize,
        fontWeight: 800,
        textAlign: "center",
        lineHeight: 1.25,
        maxWidth: 960,
        textShadow: `${shadow},0 6px 18px rgba(0,0,0,.6)`,
        opacity: t,
        transform: `translateY(${(1 - t) * 30}px)`,
      }}
    >
      <RichText text={text} />
    </div>
  );
};

const HookScene: React.FC<{ hook: ReelProps["hook"] }> = ({ hook }) => (
  <AbsoluteFill>
    <Background image={hook.image} emoji={hook.emoji} index={0} />
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", paddingTop: 240 }}>
      <YellowBox size={96}>
        {hook.lines.map((line, i) => (
          <div key={i}>
            <RichText text={line} />
          </div>
        ))}
      </YellowBox>
    </AbsoluteFill>
  </AbsoluteFill>
);

const ItemScene: React.FC<{ scene: Scene; index: number }> = ({ scene, index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const badge = spring({ frame: frame - 4, fps, config: { damping: 10 } });

  return (
    <AbsoluteFill>
      <Background image={scene.image} emoji={scene.emoji} index={index + 1} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 36, paddingTop: 420 }}>
        <div
          style={{
            width: 150,
            height: 150,
            borderRadius: "50%",
            background: THEME.badgeColor,
            color: "#fff",
            fontSize: 96,
            fontWeight: 900,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            border: "8px solid #fff",
            transform: `scale(${badge})`,
          }}
        >
          {index + 1}
        </div>
        <YellowBox>
          <RichText text={scene.title} />
        </YellowBox>
        <OutlinedText text={scene.benefit} delay={8} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const OutroScene: React.FC<{ outro: ReelProps["outro"]; index: number }> = ({ outro, index }) => (
  <AbsoluteFill>
    <Background emoji="❤️" index={index} />
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", paddingTop: 240 }}>
      <YellowBox size={88}>
        <RichText text={outro.text} />
      </YellowBox>
    </AbsoluteFill>
  </AbsoluteFill>
);

export const Reel: React.FC<ReelProps> = (props) => {
  const { fps } = useVideoConfig();
  const f = (sec: number) => Math.round(sec * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000", fontFamily }}>
      <Series>
        <Series.Sequence durationInFrames={f(props.hook.seconds)}>
          <HookScene hook={props.hook} />
        </Series.Sequence>
        {props.scenes.map((scene, i) => (
          <Series.Sequence key={i} durationInFrames={f(scene.seconds)}>
            <ItemScene scene={scene} index={i} />
          </Series.Sequence>
        ))}
        <Series.Sequence durationInFrames={f(props.outro.seconds)}>
          <OutroScene outro={props.outro} index={props.scenes.length + 1} />
        </Series.Sequence>
      </Series>

      {/* Câu miễn trừ cố định phía trên, tránh vùng caption của Reels ở dưới */}
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 120 }}>
        <div
          style={{
            color: "#fff",
            fontSize: 30,
            fontWeight: 600,
            background: "rgba(0,0,0,.45)",
            padding: "8px 22px",
            borderRadius: 40,
          }}
        >
          {props.disclaimer}
        </div>
      </AbsoluteFill>

      {props.music ? <Audio src={staticFile(`music/${props.music}`)} volume={props.musicVolume ?? 0.25} /> : null}
    </AbsoluteFill>
  );
};
