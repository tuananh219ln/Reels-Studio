"use client";

import { PauseCircleOutlined, PlayCircleOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Checkbox,
  ColorPicker,
  Flex,
  Segmented,
  Select,
  Slider,
  Switch,
  Tooltip,
  Typography,
} from "antd";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type VideoDefaults, type VideoOptions, type Voice } from "@/lib/api";
import { palette, STYLES, SWATCHES, toHex, warnings, type Style } from "./textPalette";

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
function Sample({ style, textColor, accentColor }: { style: Style; textColor: string; accentColor: string }) {
  const drawn = palette(style, textColor, "auto", accentColor);
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

/** One colour: the style's own, a swatch, or any colour from the picker; `name` prefixes each choice's label. */
function ColorChoice({
  name,
  value,
  onChange,
  disabled,
}: {
  name: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const hex = toHex(value);
  const custom = hex !== null && !SWATCHES.some((swatch) => swatch.hex === hex);
  const ring = (checked: boolean) => ({
    border: `1px solid ${checked ? "#1677ff" : "#d9d9d9"}`,
    boxShadow: checked ? "0 0 0 1px #1677ff" : undefined,
    cursor: disabled ? "not-allowed" : "pointer",
  });
  return (
    <Flex wrap gap={8} align="center" role="radiogroup" aria-label={name}>
      <button
        type="button"
        role="radio"
        aria-checked={hex === null}
        aria-label={`${name} Theo kiểu`}
        disabled={disabled}
        onClick={() => onChange("auto")}
        style={{ ...ring(hex === null), padding: "3px 10px", borderRadius: 6, background: "none" }}
      >
        <Typography.Text style={{ fontSize: 13 }}>Theo kiểu</Typography.Text>
      </button>
      {SWATCHES.map((swatch) => (
        <Tooltip key={swatch.hex} title={swatch.label}>
          <button
            type="button"
            role="radio"
            aria-checked={hex === swatch.hex}
            aria-label={`${name} ${swatch.label}`}
            disabled={disabled}
            onClick={() => onChange(swatch.hex)}
            style={{
              ...ring(hex === swatch.hex),
              width: 26,
              height: 26,
              padding: 0,
              borderRadius: "50%",
              background: swatch.hex,
              outline: "1px solid rgba(0,0,0,0.15)",
              outlineOffset: -3,
            }}
          />
        </Tooltip>
      ))}
      <ColorPicker
        value={hex ?? "#FFFFFF"}
        disabled={disabled}
        disabledAlpha
        disabledFormat
        onChangeComplete={(color) => onChange(color.toHexString().toUpperCase())}
      >
        <button
          type="button"
          role="radio"
          aria-checked={custom}
          aria-label={`${name} Tuỳ chỉnh`}
          disabled={disabled}
          style={{
            ...ring(custom),
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "3px 10px",
            borderRadius: 6,
            background: "none",
          }}
        >
          <span
            style={{
              width: 14,
              height: 14,
              borderRadius: "50%",
              background: custom ? hex : "conic-gradient(red, yellow, lime, aqua, blue, magenta, red)",
              border: "1px solid rgba(0,0,0,0.25)",
            }}
          />
          <Typography.Text style={{ fontSize: 13 }}>{custom ? hex : "Tuỳ chỉnh"}</Typography.Text>
        </button>
      </ColorPicker>
    </Flex>
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
    return (
      <Typography.Text type="warning">
        {voices.error} <Link href="/settings/sources">Mở Nguồn tư liệu</Link>
      </Typography.Text>
    );
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

/** The text box style, chosen from small previews, its colours, and the narration captions. */
export function TextSettings({ values, onChange, disabled }: Props) {
  const hasBox = values.text_style !== "none";
  const problems = warnings(
    palette(values.text_style, values.text_color, values.box_color, values.accent_color),
    hasBox,
  );
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
                  // The style brings its own box (or outline); the text colours stay.
                  onClick={() => onChange({ text_style: style.value, box_color: "auto" })}
                  style={{
                    width: 64,
                    padding: 0,
                    border: `2px solid ${checked ? "#1677ff" : "transparent"}`,
                    borderRadius: 8,
                    background: "none",
                    cursor: disabled ? "not-allowed" : "pointer",
                  }}
                >
                  <Sample style={style.value} textColor={values.text_color} accentColor={values.accent_color} />
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
        <Field label="Màu chữ">
          <ColorChoice
            name="Màu"
            value={values.text_color}
            disabled={disabled}
            onChange={(text_color) => onChange({ text_color })}
          />
        </Field>
        <Field label="Màu chữ đánh dấu" hint="Chữ đánh dấu *như thế này*; “Theo kiểu” tự giữ một màu khác chữ thường.">
          <ColorChoice
            name="Đánh dấu"
            value={values.accent_color}
            disabled={disabled}
            onChange={(accent_color) => onChange({ accent_color })}
          />
        </Field>
        <Field label={hasBox ? "Màu nền hộp" : "Màu viền chữ"}>
          <ColorChoice
            name={hasBox ? "Nền" : "Viền"}
            value={values.box_color}
            disabled={disabled}
            onChange={(box_color) => onChange({ box_color })}
          />
        </Field>
        {problems.length > 0 && (
          <Typography.Text type="warning" data-testid="color-warning">
            {problems.join(" ")} Vẫn render được, nhưng nên chọn màu khác.
          </Typography.Text>
        )}
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
