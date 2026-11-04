"use client";

import { PauseCircleOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { Button, Card, Checkbox, Flex, Segmented, Select, Slider, Switch, Tooltip, Typography } from "antd";
import type { SliderSingleProps } from "antd";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, errorMessage, type VideoDefaults, type VideoOptions, type Voice } from "@/lib/api";
import { ColorChoice } from "./textControls";
import { OPACITIES, palette, warnings } from "./textPalette";
import { TextStyleCards } from "./TextStyleCards";

/** The values these sections edit: a video's options plus its narration switch (and, for defaults, music level). */
export type SettingsValues = VideoOptions & { voice_enabled: boolean; music_volume?: number };

type Props = {
  values: SettingsValues;
  onChange: (changes: Partial<VideoDefaults>) => void;
  disabled?: boolean;
};

// The reading speed slider (api tts.MIN_SPEED, MAX_SPEED, SPEED_STEP).
const SPEED_MIN = 0.7;
const SPEED_MAX = 1.3;
const SPEED_STEP = 0.05;
// The end labels sit inside the rail instead of centred on its ends, where they spilled out of the card.
const SPEED_MARKS = {
  [SPEED_MIN]: { label: "Chậm", style: { transform: "translateX(0)" } },
  1: "Vừa",
  [SPEED_MAX]: { label: "Nhanh", style: { transform: "translateX(-100%)" } },
};
const speedText = (speed: number) => `${speed.toFixed(2).replace(".", ",")}×`;
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
        {voices.error}{" "}
        <Link prefetch={false} href="/settings/sources">
          Mở Nguồn tư liệu
        </Link>
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
          label: `${voice.name}${voice.id === voices?.defaultId ? " (mặc định)" : ""}${voice.description ? `, ${voice.description}` : ""}`,
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
        <SliderField
          label="Tốc độ đọc"
          format={speedText}
          hint="Đổi giọng hoặc tốc độ thì lần render sau tạo lại lời đọc (tốn ký tự)."
          min={SPEED_MIN}
          max={SPEED_MAX}
          step={SPEED_STEP}
          marks={SPEED_MARKS}
          value={values.voice_speed}
          disabled={disabled || off}
          onSave={(speed) => onChange({ voice_speed: Math.round(speed * 100) / 100 })}
        />
        <SliderField
          label="Âm lượng giọng"
          format={percentText}
          min={0}
          max={100}
          step={5}
          value={values.voice_volume}
          disabled={disabled || off}
          onSave={(voice_volume) => onChange({ voice_volume })}
        />
        {showMusicVolume && values.music_volume !== undefined && (
          <SliderField
            label="Âm lượng nhạc"
            format={percentText}
            min={0}
            max={100}
            step={5}
            value={values.music_volume}
            disabled={disabled}
            onSave={(music_volume) => onChange({ music_volume })}
          />
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

const percentText = (value: number) => `${value}%`;

/** A slider whose handle and label follow the mouse while it moves; the value is saved only when it is let go,
 * so a drag makes one save. */
function SliderField({
  label,
  format,
  hint,
  min,
  max,
  step,
  marks,
  value,
  disabled,
  onSave,
}: {
  label: string;
  format: (value: number) => string;
  hint?: string;
  min: number;
  max: number;
  step: number;
  marks?: SliderSingleProps["marks"];
  value: number;
  disabled?: boolean;
  onSave: (value: number) => void;
}) {
  const [moving, setMoving] = useState<number | null>(null);
  const shown = moving ?? value;
  return (
    <Field label={`${label}: ${format(shown)}`} hint={hint}>
      <Slider
        ariaLabelForHandle={label}
        min={min}
        max={max}
        step={step}
        marks={marks}
        tooltip={{ formatter: (current) => (current === undefined ? null : format(current)) }}
        value={shown}
        disabled={disabled}
        onChange={setMoving}
        onChangeComplete={(done) => {
          setMoving(null);
          if (done !== value) onSave(done);
        }}
      />
    </Field>
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
type Look = Pick<VideoOptions, "text_style" | "text_color" | "box_color" | "accent_color" | "box_opacity">;
const TITLE_FIELDS = {
  text_style: "title_text_style",
  text_color: "title_text_color",
  box_color: "title_box_color",
  accent_color: "title_accent_color",
  box_opacity: "title_box_opacity",
} as const;
const AUTO_TITLE = {
  title_text_style: "same",
  title_text_color: "auto",
  title_box_color: "auto",
  title_accent_color: "auto",
  title_box_opacity: "auto",
} as const;

const sceneLook = (values: SettingsValues): Look => ({
  text_style: values.text_style,
  text_color: values.text_color,
  box_color: values.box_color,
  accent_color: values.accent_color,
  box_opacity: values.box_opacity,
});

/** What the title is drawn with (RenderOptions.title_palette): its own look, the old yellow box, or the scenes'. */
function titleLook(values: SettingsValues): Look {
  // An api older than the page leaves the title fields out: the title then follows the older choices.
  if (values.title_text_style && values.title_text_style !== "same") {
    return {
      text_style: values.title_text_style,
      text_color: values.title_text_color,
      box_color: values.title_box_color,
      accent_color: values.title_accent_color,
      box_opacity: values.title_box_opacity,
    };
  }
  if (values.title_style === "yellow") {
    return { text_style: "yellow", text_color: "auto", box_color: "auto", accent_color: "auto", box_opacity: "auto" };
  }
  return sceneLook(values);
}

/** The title's own look as options; the older "Hộp vàng" choice gives way to it. */
const asTitle = (look: Look): Partial<VideoOptions> => ({
  title_style: "same",
  ...Object.fromEntries(Object.entries(look).map(([name, value]) => [TITLE_FIELDS[name as keyof Look], value])),
});

/** The style cards and colour rows for one look: the content scenes', or the title's own. */
function LookControls({
  look,
  onChange,
  disabled,
}: {
  look: Look;
  onChange: (changes: Partial<Look>) => void;
  disabled?: boolean;
}) {
  const hasBox = look.text_style !== "none" && look.box_opacity !== "none";
  const problems = warnings(
    palette(look.text_style, look.text_color, look.box_color, look.accent_color, look.box_opacity),
    hasBox,
  );
  return (
    <>
      <Field label="Kiểu hộp chữ" hint="Kiểu dùng chung cả đội. Chỉnh màu bên dưới không làm đổi kiểu.">
        <TextStyleCards values={look} onChange={onChange} disabled={disabled} />
      </Field>
      <Field label="Màu chữ">
        <ColorChoice
          name="Màu"
          value={look.text_color}
          disabled={disabled}
          onChange={(text_color) => onChange({ text_color })}
        />
      </Field>
      <Field label="Màu chữ đánh dấu" hint="Chữ đánh dấu *như thế này*; “Theo kiểu” tự giữ một màu khác chữ thường.">
        <ColorChoice
          name="Đánh dấu"
          value={look.accent_color}
          disabled={disabled}
          onChange={(accent_color) => onChange({ accent_color })}
        />
      </Field>
      <Field label={hasBox ? "Màu nền hộp" : "Màu viền chữ"}>
        <ColorChoice
          name={hasBox ? "Nền" : "Viền"}
          value={look.box_color}
          disabled={disabled}
          onChange={(box_color) => onChange({ box_color })}
        />
      </Field>
      {look.text_style !== "none" && (
        <Field label="Độ trong của hộp" hint="Không nền: chữ có viền như Không hộp, màu nền thành màu viền.">
          <Segmented
            aria-label="Độ trong của hộp"
            // Five choices outgrow a phone: they scroll inside instead of widening the page.
            style={{ maxWidth: "100%", overflowX: "auto" }}
            options={[
              { value: "auto", label: "Theo kiểu" },
              ...OPACITIES.map(({ value, label }) => ({ value, label })),
            ]}
            value={look.box_opacity}
            disabled={disabled}
            onChange={(box_opacity) => onChange({ box_opacity: box_opacity as VideoOptions["box_opacity"] })}
          />
        </Field>
      )}
      {problems.length > 0 && (
        <Typography.Text type="warning" data-testid="color-warning">
          {problems.join(" ")} Vẫn render được, nhưng nên chọn màu khác.
        </Typography.Text>
      )}
    </>
  );
}

/** The text boxes (the content scenes', and the title's when it has its own look) and the narration captions. */
export function TextSettings({ values, onChange, disabled }: Props) {
  const [target, setTarget] = useState<"scenes" | "title">("scenes");
  const title = titleLook(values);
  const followsScenes =
    (!values.title_text_style || values.title_text_style === "same") && values.title_style !== "yellow";
  return (
    <Card title="Chữ & phụ đề" size="small" data-testid="text-settings">
      <Flex vertical gap={14}>
        <Segmented
          aria-label="Chỉnh chữ cho"
          block
          options={[
            { value: "scenes", label: "Các cảnh" },
            { value: "title", label: "Tiêu đề" },
          ]}
          value={target}
          onChange={(value) => setTarget(value as "scenes" | "title")}
        />
        {target === "scenes" ? (
          <>
            <LookControls look={sceneLook(values)} onChange={onChange} disabled={disabled} />
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
          </>
        ) : (
          <>
            <Checkbox
              checked={followsScenes}
              disabled={disabled}
              // Leaving the scenes' look starts the title from it; going back drops the title's own.
              onChange={(event) =>
                onChange(event.target.checked ? { title_style: "same", ...AUTO_TITLE } : asTitle(title))
              }
            >
              Tiêu đề giống các cảnh
            </Checkbox>
            {!followsScenes && (
              <LookControls
                look={title}
                onChange={(changes) => onChange(asTitle({ ...title, ...changes }))}
                disabled={disabled}
              />
            )}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Tiêu đề cũng là ảnh thumbnail của video. Phụ đề không hiện trên cảnh tiêu đề.
            </Typography.Text>
          </>
        )}
      </Flex>
    </Card>
  );
}
