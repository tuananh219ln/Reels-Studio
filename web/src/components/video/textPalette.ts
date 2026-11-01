/**
 * What the renderer draws for a text box style and its colours (reels_render.textbox.palette_for), so the small
 * style samples and the readability warnings match the MP4. Keep the two in step.
 */
import type { VideoOptions } from "@/lib/api";

export type Style = VideoOptions["text_style"];

const BLACK = "#111111";
const YELLOW = "#FFD60A";
const RED = "#E10600";
const WHITE = "#FFFFFF";

export const STYLES: {
  value: Style;
  label: string;
  box: string | null;
  alpha: number;
  text: string;
  accent: string;
}[] = [
  { value: "yellow", label: "Vàng", box: YELLOW, alpha: 1, text: BLACK, accent: RED },
  { value: "white", label: "Trắng", box: WHITE, alpha: 1, text: BLACK, accent: RED },
  { value: "dark", label: "Tối", box: BLACK, alpha: 224 / 255, text: WHITE, accent: YELLOW },
  { value: "red", label: "Đỏ", box: RED, alpha: 1, text: WHITE, accent: YELLOW },
  { value: "none", label: "Không hộp", box: null, alpha: 0, text: WHITE, accent: YELLOW },
];

/** The named text colours stored before custom ones existed; each is its hex value. */
const NAMED: Record<string, string> = { white: WHITE, black: BLACK, yellow: YELLOW, red: RED };
const ALTERNATE: Record<Style, string> = { yellow: BLACK, white: BLACK, dark: WHITE, red: WHITE, none: RED };
const FALLBACK = [RED, YELLOW, WHITE, BLACK];

/** The colours offered as swatches; any other comes from the colour picker. */
export const SWATCHES = [
  { label: "Trắng", hex: WHITE },
  { label: "Đen", hex: BLACK },
  { label: "Vàng", hex: YELLOW },
  { label: "Đỏ", hex: RED },
  { label: "Cam", hex: "#FF7A00" },
  { label: "Xanh lá", hex: "#16A34A" },
  { label: "Xanh dương", hex: "#1D4ED8" },
  { label: "Hồng", hex: "#EC4899" },
];

/** A stored colour as hex: "auto" stays null, a named one becomes its hex. A missing one (from an api older
 * than the page) or one that is not a colour counts as "auto". */
export function toHex(value: string | undefined): string | null {
  const hex = value === undefined ? undefined : (NAMED[value] ?? value);
  return hex !== undefined && /^#[0-9a-f]{6}$/i.test(hex) ? hex.toUpperCase() : null;
}

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16)) as [number, number, number];
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((value) => {
    const channel = value / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** WCAG contrast ratio, 1 (none) to 21 (black on white). */
export function contrast(first: string, second: string): number {
  const [light, dark] = [luminance(first), luminance(second)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

function distance(first: string, second: string): number {
  const [a, b] = [rgb(first), rgb(second)];
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

export type Drawn = {
  box: string | null; // CSS colour of the box, null without one
  ground: string; // what the letters sit on: the box's colour, or the outline's
  text: string;
  accent: string;
  outline: string | null;
};

export function palette(
  style: Style,
  textColor: string = "auto",
  boxColor: string = "auto",
  accentColor: string = "auto",
): Drawn {
  // An unknown style (e.g. from an api older than the page) draws the original yellow box.
  const base = STYLES.find((item) => item.value === style) ?? STYLES[0];
  const text = toHex(textColor) ?? base.text;
  let box: string | null = null;
  let outline: string | null = null;
  let ground: string;
  if (base.box === null) {
    outline = toHex(boxColor) ?? (luminance(text) < 0.05 ? WHITE : "#000000");
    ground = outline;
  } else {
    ground = toHex(boxColor) ?? base.box;
    const [r, g, b] = rgb(ground);
    box = base.alpha < 1 ? `rgba(${r},${g},${b},${base.alpha.toFixed(2)})` : ground;
  }
  const accent =
    toHex(accentColor) ??
    [base.accent, ALTERNATE[base.value], ...FALLBACK].find(
      (candidate) => distance(candidate, text) >= 100 && contrast(candidate, ground) >= 3,
    ) ??
    base.accent;
  return { box, ground, text, accent, outline };
}

/** Readability warnings for the colours chosen, shown under the colour pickers. */
export function warnings(drawn: Drawn, hasBox: boolean): string[] {
  const where = hasBox ? "nền hộp" : "viền chữ";
  const found = [];
  if (contrast(drawn.text, drawn.ground) < 3) {
    found.push(`Chữ khó đọc trên ${where} này.`);
  }
  if (contrast(drawn.accent, drawn.ground) < 3) {
    found.push(`Chữ đánh dấu khó đọc trên ${where} này.`);
  }
  if (distance(drawn.accent, drawn.text) < 100) {
    found.push("Chữ đánh dấu gần trùng màu chữ thường, sẽ không nổi bật.");
  }
  return found;
}
