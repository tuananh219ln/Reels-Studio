import type { VideoLayout } from "@/lib/api";
import { FRAME_HEIGHT, FRAME_WIDTH } from "./TextPositionModal";

/** The stored badge picture (reels_render.logo): 686 px across, its white ring 564 px, 61 px of shadow room round it. */
const BADGE_CANVAS = 686;
const BADGE_RING = 564;
const BADGE_PAD = 61;

/** Where the badge picture goes over a 9:16 frame so that its ring is the logo's box, as the renderer lays it. */
export function badgeStyle({ x, y, size }: Pick<VideoLayout["logo"], "x" | "y" | "size">): React.CSSProperties {
  const scale = size / BADGE_RING;
  return {
    position: "absolute",
    left: `${((x - BADGE_PAD * scale) / FRAME_WIDTH) * 100}%`,
    top: `${((y - BADGE_PAD * scale) / FRAME_HEIGHT) * 100}%`,
    width: `${((BADGE_CANVAS * scale) / FRAME_WIDTH) * 100}%`,
  };
}
