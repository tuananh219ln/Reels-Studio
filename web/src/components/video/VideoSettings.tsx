"use client";

import { PauseCircleOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { Button, Card, Checkbox, Flex, Segmented, Select, Slider, Switch, Tooltip, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type VideoDefaults, type VideoOptions, type Voice } from "@/lib/api";

/** The values these sections edit: a video's options plus its narration switch (and, for defaults, music level). */
export type SettingsValues = VideoOptions & { voice_enabled: boolean; music_volume?: number };

type Props = {
  values: SettingsValues;
  onChange: (changes: Partial<VideoDefaults>) => void;
  disabled?: boolean;
};

const SPEEDS = [
  { value: "slow", label: "Chậm" },
  { value: "normal", label: "Vừa" },
  { value: "fast", label: "Nhanh" },
];
const TRANSITIONS = [
  { value: "fade", label: "Mờ dần" },
  { value: "cut", label: "Cắt thẳng" },
  { value: "slide", label: "Trượt" },
];
const MOTIONS = [
  { value: "zoom_in", label: "Zoom vào" },
  { value: "zoom_out", label: "Zoom ra" },
  { value: "pan", label: "Lia ngang" },
  { value: "static", label: "Đứng yên" },
];
const ZOOMS = [
  { value: "light", label: "Nhẹ" },
  { value: "medium", label: "Vừa" },
  { value: "strong", label: "Mạnh" },
];
const CAPTIONS = [
  { value: "off", label: "Tắt" },
  { value: "phrase", label: "Từng cụm" },
  { value: "word", label: "Từng từ" },
];
const TITLE_STYLES: { value: VideoOptions["title_style"]; label: string }[] = [
  { value: "same", label: "Giống cảnh" },
  { value: "yellow", label: "Hộp vàng" },
];
// The renderer's palettes (reels_render.textbox), drawn small so members choose by sight.
type Style = VideoOptions["text_style"];
type TextColor = VideoOptions["text_color"];
const STYLES: { value: Style; label: string; box: string | null; text: string; accent: string }[] = [
  { value: "yellow", label: "Vàng", box: "#FFD60A", text: "#111111", accent: "#E10600" },
  { value: "white", label: "Trắng", box: "#FFFFFF", text: "#111111", accent: "#E10600" },
  { value: "dark", label: "Tối", box: "rgba(17,17,17,0.88)", text: "#FFFFFF", accent: "#FFD60A" },
  { value: "red", label: "Đỏ", box: "#E10600", text: "#FFFFFF", accent: "#FFD60A" },
  { value: "none", label: "Không hộp", box: null, text: "#FFFFFF", accent: "#FFD60A" },
];
const COLORS: { value: Exclude<TextColor, "auto">; label: string; hex: string }[] = [
  { value: "white", label: "Trắng", hex: "#FFFFFF" },
  { value: "black", label: "Đen", hex: "#111111" },
  { value: "yellow", label: "Vàng", hex: "#FFD60A" },
  { value: "red", label: "Đỏ", hex: "#E10600" },
];
// Colours too faint on a box (textbox.CLASHES): not offered with that box.
const CLASHES: Partial<Record<Style, TextColor[]>> = {
  yellow: ["yellow", "white"],
  white: ["white", "yellow"],
  dark: ["black"],
  red: ["red"],
};

const clashes = (style: Style, color: TextColor) => CLASHES[style]?.includes(color) ?? false;

/** What the renderer draws for a style and colour (textbox.palette_for). */
function look(style: Style, color: TextColor) {
  // An unknown value (e.g. from an api older than the page) draws the original yellow box.
  const base = STYLES.find((item) => item.value === style) ?? STYLES[0];
  const outline = base.box === null ? (color === "black" ? "#FFFFFF" : "#000000") : null;
  const chosen = COLORS.find((item) => item.value === color);
  if (!chosen || clashes(base.value, color)) {
    return { ...base, outline };
  }
  const text = chosen.hex;
  const accent =
    base.box === null
      ? color === "black" || color === "yellow"
        ? "#E10600"
        : base.accent
      : text === base.accent
        ? base.text
        : base.accent;
  return { ...base, text, accent, outline };
}

function Sample({ style, color }: { style: Style; color: TextColor }) {
  const drawn = look(style, color);
  const stroke = drawn.outline
    ? [-1, 0, 1].flatMap((x) => [-1, 0, 1].map((y) => `${x}px ${y}px 0 ${drawn.outline}`)).join(", ")
    : undefined;
  return (
    <div
      style={{
        aspectRatio: "9 / 16",
        borderRadius: 6,
        background: "linear-gradient(160deg, #9bb57a 0%, #c98b4b 55%, #6d4b2f 100%)",
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "center",
        paddingBottom: 18,
      }}
    >
      <span
        style={{
          background: drawn.box ?? "none",
          color: drawn.text,
          textShadow: stroke,
          fontWeight: 900,
          fontSize: 9,
          lineHeight: 1.2,
          padding: "3px 5px",
          borderRadius: 3,
          textAlign: "center",
        }}
      >
        CÁ NHỎ
        <br />
        <span style={{ color: drawn.accent }}>CANXI</span>
      </span>
    </div>
  );
}

let voiceCache: Promise<{ default_id: string; voices: Voice[] }> | null = null;

/** The ElevenLabs voices, fetched once per page load. */
function useVoices() {
  const [state, setState] = useState<{ defaultId: string; voices: Voice[]; error: string | null } | null>(null);
  useEffect(() => {
    voiceCache ??= api<{ default_id: string; voices: Voice[] }>("/settings/voices");
    voiceCache
      .then((data) => setState({ defaultId: data.default_id, voices: data.voices, error: null }))
      .catch((err) => {
        voiceCache = null;
        setState({ defaultId: "", voices: [], error: errorMessage(err) });
      });
  }, []);
  return state;
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <Typography.Text strong style={{ display: "block", marginBottom: 4 }}>
        {label}
      </Typography.Text>
      {children}
      {hint && (
        <Typography.Text type="secondary" style={{ display: "block", fontSize: 12, marginTop: 4 }}>
          {hint}
        </Typography.Text>
      )}
    </div>
  );
}

function VoicePicker({ values, onChange, disabled }: Props) {
  const voices = useVoices();
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const chosen = values.voice_id || voices?.defaultId || "";
  const sample = voices?.voices.find((voice) => voice.id === chosen)?.preview_url;

  function listen() {
    if (playing) {
      audio.current?.pause();
      setPlaying(false);
      return;
    }
    if (!sample) {
      return;
    }
    audio.current?.pause();
    audio.current = new Audio(sample);
    audio.current.onended = () => setPlaying(false);
    void audio.current.play().then(() => setPlaying(true));
  }

  if (voices?.error) {
    return <Typography.Text type="warning">{voices.error}</Typography.Text>;
  }
  return (
    <Flex gap={8}>
      <Select
        aria-label="Giọng đọc"
        style={{ flex: 1, minWidth: 0 }}
        loading={voices === null}
        disabled={disabled}
        value={chosen || undefined}
        showSearch={{ optionFilterProp: "label" }}
        onChange={(id) => onChange({ voice_id: id === voices?.defaultId ? "" : id })}
        options={(voices?.voices ?? []).map((voice) => ({
          value: voice.id,
          label: `${voice.name}${voice.id === voices?.defaultId ? " (mặc định)" : ""}${voice.description ? ` · ${voice.description}` : ""}`,
        }))}
      />
      <Tooltip title={sample ? "Nghe thử giọng mẫu (không tốn ký tự)" : "Giọng này không có bản nghe thử"}>
        <Button
          aria-label="Nghe thử"
          icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          disabled={!sample}
          onClick={listen}
        />
      </Tooltip>
    </Flex>
  );
}

/** Narration: on or off, the voice, its speed and level, and whether the music steps back for it. */
export function AudioSettings({ values, onChange, disabled, showMusicVolume }: Props & { showMusicVolume?: boolean }) {
  const off = !values.voice_enabled;
  return (
    <Card title="Âm thanh" size="small" data-testid="audio-settings">
      <Flex vertical gap={14}>
        <Flex gap={8} align="center">
          <Switch
            aria-label="Đọc lời từng cảnh"
            checked={values.voice_enabled}
            disabled={disabled}
            onChange={(voice_enabled) => onChange({ voice_enabled })}
          />
          <Typography.Text>Đọc lời từng cảnh (ElevenLabs)</Typography.Text>
        </Flex>
        <Field label="Giọng">
          <VoicePicker values={values} onChange={onChange} disabled={disabled || off} />
        </Field>
        <Field label="Tốc độ đọc" hint="Đổi giọng hoặc tốc độ thì lần render sau tạo lại lời đọc (tốn ký tự).">
          <Segmented
            aria-label="Tốc độ đọc"
            options={SPEEDS}
            value={values.voice_speed}
            disabled={disabled || off}
            onChange={(voice_speed) => onChange({ voice_speed: voice_speed as VideoOptions["voice_speed"] })}
          />
        </Field>
        <Field label={`Âm lượng giọng: ${values.voice_volume}%`}>
          <Slider
            aria-label="Âm lượng giọng"
            min={0}
            max={100}
            step={5}
            value={values.voice_volume}
            disabled={disabled || off}
            onChangeComplete={(voice_volume) => onChange({ voice_volume })}
          />
        </Field>
        {showMusicVolume && values.music_volume !== undefined && (
          <Field label={`Âm lượng nhạc: ${values.music_volume}%`}>
            <Slider
              aria-label="Âm lượng nhạc"
              min={0}
              max={100}
              step={5}
              value={values.music_volume}
              disabled={disabled}
              onChangeComplete={(music_volume) => onChange({ music_volume })}
            />
          </Field>
        )}
        <Checkbox
          checked={values.ducking}
          disabled={disabled || off}
          onChange={(event) => onChange({ ducking: event.target.checked })}
        >
          Nhỏ nhạc khi có giọng đọc
        </Checkbox>
      </Flex>
    </Card>
  );
}

/** How photo scenes move and how scenes are joined. */
export function MotionSettings({ values, onChange, disabled }: Props) {
  return (
    <Card title="Hình ảnh" size="small" data-testid="motion-settings">
      <Flex vertical gap={14}>
        <Field label="Chuyển cảnh">
          <Segmented
            aria-label="Chuyển cảnh"
            options={TRANSITIONS}
            value={values.transition}
            disabled={disabled}
            onChange={(transition) => onChange({ transition: transition as VideoOptions["transition"] })}
          />
        </Field>
        <Field label="Chuyển động ảnh" hint="Cảnh dùng video không có chuyển động thêm.">
          <Segmented
            aria-label="Chuyển động ảnh"
            options={MOTIONS}
            value={values.motion}
            disabled={disabled}
            onChange={(motion) => onChange({ motion: motion as VideoOptions["motion"] })}
          />
        </Field>
        <Field label="Độ zoom">
          <Segmented
            aria-label="Độ zoom"
            options={ZOOMS}
            value={values.zoom}
            disabled={disabled || values.motion === "static"}
            onChange={(zoom) => onChange({ zoom: zoom as VideoOptions["zoom"] })}
          />
        </Field>
      </Flex>
    </Card>
  );
}

/** The text box style, chosen from small previews, and the narration captions. */
export function TextSettings({ values, onChange, disabled }: Props) {
  return (
    <Card title="Chữ & phụ đề" size="small" data-testid="text-settings">
      <Flex vertical gap={14}>
        <Field label="Kiểu hộp chữ">
          <Flex wrap gap={10} role="radiogroup" aria-label="Kiểu hộp chữ">
            {STYLES.map((style) => {
              const checked = values.text_style === style.value;
              return (
                <button
                  key={style.value}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  aria-label={`Kiểu ${style.label}`}
                  disabled={disabled}
                  // A colour too faint on the new box goes back to the box's own.
                  onClick={() =>
                    onChange(
                      clashes(style.value, values.text_color)
                        ? { text_style: style.value, text_color: "auto" }
                        : { text_style: style.value },
                    )
                  }
                  style={{
                    width: 64,
                    padding: 0,
                    border: `2px solid ${checked ? "#1677ff" : "transparent"}`,
                    borderRadius: 8,
                    background: "none",
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  <Sample style={style.value} color={values.text_color} />
                  <Typography.Text style={{ fontSize: 12 }}>{style.label}</Typography.Text>
                </button>
              );
            })}
          </Flex>
        </Field>
        <Field label="Kiểu tiêu đề" hint="Hộp vàng giữ tiêu đề dễ đọc dù các cảnh dùng kiểu khác.">
          <Segmented
            aria-label="Kiểu tiêu đề"
            options={TITLE_STYLES}
            value={values.title_style}
            disabled={disabled}
            onChange={(title_style) => onChange({ title_style: title_style as VideoOptions["title_style"] })}
          />
        </Field>
        <Field label="Màu chữ" hint="Chữ đánh dấu *như thế này* giữ một màu khác để vẫn nổi bật.">
          <Flex wrap gap={8} role="radiogroup" aria-label="Màu chữ">
            {[{ value: "auto" as const, label: "Theo kiểu", hex: "" }, ...COLORS].map((color) => {
              const checked = values.text_color === color.value;
              const faint = clashes(values.text_style, color.value);
              const button = (
                <button
                  key={color.value}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  aria-label={`Màu ${color.label}`}
                  disabled={disabled || faint}
                  onClick={() => onChange({ text_color: color.value })}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "4px 10px",
                    border: `1px solid ${checked ? "#1677ff" : "#d9d9d9"}`,
                    boxShadow: checked ? "0 0 0 1px #1677ff" : undefined,
                    borderRadius: 6,
                    background: "none",
                    opacity: faint ? 0.4 : 1,
                    cursor: disabled || faint ? "not-allowed" : "pointer",
                  }}
                >
                  {color.hex && (
                    <span
                      style={{
                        width: 14,
                        height: 14,
                        borderRadius: "50%",
                        background: color.hex,
                        border: "1px solid rgba(0,0,0,0.25)",
                      }}
                    />
                  )}
                  <Typography.Text style={{ fontSize: 13 }}>{color.label}</Typography.Text>
                </button>
              );
              return faint ? (
                <Tooltip key={color.value} title="Khó đọc trên kiểu hộp này">
                  {button}
                </Tooltip>
              ) : (
                button
              );
            })}
          </Flex>
        </Field>
        <Field
          label="Phụ đề theo giọng đọc"
          hint={
            values.voice_enabled
              ? "Chữ trắng trên nền tối, ngay trên hộp chữ của cảnh; “Từng từ” tô vàng từ đang đọc."
              : "Cần bật giọng đọc."
          }
        >
          <Segmented
            aria-label="Phụ đề theo giọng đọc"
            options={CAPTIONS}
            value={values.captions}
            disabled={disabled || !values.voice_enabled}
            onChange={(captions) => onChange({ captions: captions as VideoOptions["captions"] })}
          />
        </Field>
      </Flex>
    </Card>
  );
}
