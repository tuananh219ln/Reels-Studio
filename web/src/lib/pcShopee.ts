/** The topic group "Ẩn chữ sau X giây" is for; the same name as api video_options.PC_SHOPEE_GROUP. */
export const PC_SHOPEE_GROUP = "PC Shopee";

export const isPcShopee = (group: string | null | undefined): boolean =>
  (group ?? "").trim().toLowerCase() === PC_SHOPEE_GROUP.toLowerCase();

/** "Thời gian hiện chữ" of a video: the four choices of the spec; null is the whole scene. */
export const TEXT_HOLD_CHOICES: { value: number | null; label: string }[] = [
  { value: null, label: "Suốt cảnh" },
  { value: 2, label: "2 giây" },
  { value: 2.5, label: "2,5 giây" },
  { value: 3.5, label: "3,5 giây" },
];

/** A scene's own hold: 1 to 6 seconds in half seconds. */
export const SCENE_HOLD_VALUES = Array.from({ length: 11 }, (_, index) => 1 + index * 0.5);
