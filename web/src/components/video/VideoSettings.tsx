"use client";

import { InfoCircleOutlined, PauseCircleOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { Button, Card, Checkbox, Flex, Segmented, Select, Slider, Switch, Tooltip, Typography } from "antd";
import type { SelectProps, SliderSingleProps } from "antd";
import Link from "next/link";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { COLORS } from "@/app/theme";
import {
  api,
  errorMessage,
  type VideoDefaults,
  type VideoOptions,
  type Voice,
  type VoiceList,
  formatDecimal,
} from "@/lib/api";
import { ColorChoice } from "./textControls";
import { OPACITIES, palette, warnings } from "./textPalette";
import { TextStyleCards } from "./TextStyleCards";
import { VOICE_PAUSES } from "./videoModes";

/** The values these sections edit: a video's options plus its narration switch (and, for defaults, music level). */
export type SettingsValues = VideoOptions & { voice_enabled: boolean; music_volume?: number };

type Props = {
  values: SettingsValues;
  onChange: (changes: Partial<VideoDefaults>) => void;
  disabled?: boolean;
  /** Without its card: the video's "Thiết lập" tab puts each group in a panel of its own that names it. */
  bare?: boolean;
};

/** A group of settings: a card of its own, or (`bare`) just its fields inside a panel that already names it. */
function Group({
  title,
  testId,
  bare,
  children,
}: {
  title: string;
  testId: string;
  bare?: boolean;
  children: React.ReactNode;
}) {
  return bare ? (
    <div data-testid={testId}>{children}</div>
  ) : (
    <Card title={title} size="small" data-testid={testId}>
      {children}
    </Card>
  );
}

/** Fields laid out as rows: the label on the left, the control beside it, the explanation behind an ⓘ. */
const RowFields = createContext(false);
const ROW_LABEL_WIDTH = 92;

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
const speedText = (speed: number) => `${formatDecimal(speed, 2)}×`;
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
let voiceCache: Promise<VoiceList> | null = null;

/** Lists the voices again on the next picker shown, after a narration key was saved or removed. */
export function forgetVoices() {
  voiceCache = null;
}

/** The ElevenLabs and VieNeu voices, fetched once per page load. */
function useVoices() {
  const [state, setState] = useState<{
    defaultId: string;
    voices: Voice[];
    problems: string[];
    error: string | null;
  } | null>(null);
  useEffect(() => {
    voiceCache ??= api<VoiceList>("/settings/voices");
    voiceCache
      .then((data) =>
        setState({ defaultId: data.default_id, voices: data.voices, problems: data.problems ?? [], error: null }),
      )
      .catch((err) => {
        voiceCache = null;
        setState({ defaultId: "", voices: [], problems: [], error: errorMessage(err) });
      });
  }, []);
  return state;
}

const VOICE_GROUPS: { service: Voice["service"]; label: string }[] = [
  { service: "elevenlabs", label: "ElevenLabs" },
  { service: "vieneu", label: "VieNeu" },
];

function Field({
  label,
  children,
  hint,
  after,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
  /** In a row, what follows the control (a slider's value); stacked, the caller puts it in the label. */
  after?: React.ReactNode;
}) {
  const row = useContext(RowFields);
  if (row) {
    return (
      <Flex gap={8} align="center">
        <Flex gap={4} align="center" style={{ width: ROW_LABEL_WIDTH, flex: "none" }}>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            {label}
          </Typography.Text>
          {hint && (
            <Tooltip title={hint}>
              <InfoCircleOutlined aria-label={hint} style={{ fontSize: 12, color: COLORS.textSecondary }} />
            </Tooltip>
          )}
        </Flex>
        <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
        {after}
      </Flex>
    );
  }
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

/** `unset`: the voice may be left unchosen (a topic group's voice), shown as this placeholder and cleared with ×;
 * otherwise an empty voice is the server's default voice. */
export function VoicePicker({
  values,
  onChange,
  disabled,
  unset,
}: Pick<Props, "onChange" | "disabled"> & {
  values: Pick<SettingsValues, "voice_id"> & Partial<SettingsValues>;
  unset?: string;
}) {
  const voices = useVoices();
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const chosen = unset ? values.voice_id : values.voice_id || voices?.defaultId || "";
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
  const option = (voice: Voice) => ({
    value: voice.id,
    label: `${voice.name}${voice.id === voices?.defaultId ? " (mặc định)" : ""}${voice.description ? `, ${voice.description}` : ""}`,
  });
  // Grouped by service once both have voices; a single service stays a plain list, as before VieNeu.
  const groups = VOICE_GROUPS.map((group) => ({
    ...group,
    voices: (voices?.voices ?? []).filter((voice) => voice.service === group.service),
  })).filter((group) => group.voices.length > 0);
  const options: SelectProps["options"] =
    groups.length > 1
      ? groups.map((group) => ({ label: group.label, title: group.label, options: group.voices.map(option) }))
      : (voices?.voices ?? []).map(option);
  return (
    <Flex vertical gap={4}>
      <Flex gap={8}>
        <Select
          aria-label="Giọng đọc"
          style={{ flex: 1, minWidth: 0 }}
          loading={voices === null}
          disabled={disabled}
          value={chosen || undefined}
          placeholder={unset}
          allowClear={Boolean(unset)}
          showSearch={{ optionFilterProp: "label" }}
          onChange={(id) => onChange({ voice_id: unset ? (id ?? "") : id === voices?.defaultId ? "" : id })}
          options={options}
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
      {voices?.problems.map((problem) => (
        <Typography.Text key={problem} type="warning" style={{ fontSize: 12 }}>
          {problem}
        </Typography.Text>
      ))}
    </Flex>
  );
}

/** Narration: on or off, the voice, its speed and level, and whether the music steps back for it. */
export function AudioSettings({
  values,
  onChange,
  disabled,
  showMusicVolume,
  bare,
}: Props & { showMusicVolume?: boolean }) {
  const off = !values.voice_enabled;
  const voiceSwitch = (
    <Switch
      aria-label="Đọc lời từng cảnh"
      checked={values.voice_enabled}
      disabled={disabled}
      onChange={(voice_enabled) => onChange({ voice_enabled })}
    />
  );
  return (
    <Group title="Âm thanh" testId="audio-settings" bare={bare}>
      {/* Bare (the video's tab): one row per control, the switch beside the voice it turns on. */}
      <RowFields.Provider value={Boolean(bare)}>
        <Flex vertical gap={bare ? 10 : 14}>
          {bare ? (
            <Field label="Đọc lời" hint="Đọc lời từng cảnh bằng ElevenLabs hoặc VieNeu.">
              <Flex gap={8} align="flex-start">
                <div style={{ paddingTop: 6 }}>{voiceSwitch}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <VoicePicker values={values} onChange={onChange} disabled={disabled || off} />
                </div>
              </Flex>
            </Field>
          ) : (
            <>
              <Flex gap={8} align="center">
                {voiceSwitch}
                <Typography.Text>Đọc lời từng cảnh (ElevenLabs hoặc VieNeu)</Typography.Text>
              </Flex>
              <Field label="Giọng">
                <VoicePicker values={values} onChange={onChange} disabled={disabled || off} />
              </Field>
            </>
          )}
          <AudioRest values={values} onChange={onChange} disabled={disabled} showMusicVolume={showMusicVolume} />
        </Flex>
      </RowFields.Provider>
    </Group>
  );
}

/** The narration's speed, level and pause, and the music's level and ducking: the same in a card or in rows. */
function AudioRest({ values, onChange, disabled, showMusicVolume }: Props & { showMusicVolume?: boolean }) {
  const off = !values.voice_enabled;
  const row = useContext(RowFields);
  return (
    <>
      <SliderField
        label={row ? "Tốc độ" : "Tốc độ đọc"}
        name="Tốc độ đọc"
        format={speedText}
        // In rows the note sits once at the panel's foot instead.
        hint={row ? undefined : "Đổi giọng hoặc tốc độ thì lần render sau tạo lại lời đọc (tốn ký tự)."}
        min={SPEED_MIN}
        max={SPEED_MAX}
        step={SPEED_STEP}
        marks={row ? undefined : SPEED_MARKS}
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
      <Field
        label={row ? "Nghỉ sau lời" : "Nghỉ sau lời đọc"}
        hint="Khoảng lặng ở cuối mỗi cảnh có số giây tự khớp lời đọc; đổi thì các cảnh đó dài ngắn theo."
      >
        <Segmented
          aria-label="Nghỉ sau lời đọc"
          value={values.voice_pause}
          disabled={disabled || off}
          // In a row the three lengths are shown short, so they fit beside the label.
          options={
            row
              ? VOICE_PAUSES.map(({ value }) => ({ value, label: `${value.toLocaleString("vi-VN")} giây` }))
              : VOICE_PAUSES
          }
          onChange={(voice_pause) => onChange({ voice_pause: voice_pause as VideoOptions["voice_pause"] })}
        />
      </Field>
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
    </>
  );
}

const percentText = (value: number) => `${value}%`;

/** A slider whose handle and label follow the mouse while it moves; the value is saved only when it is let go,
 * so a drag makes one save. */
function SliderField({
  label,
  name = label,
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
  /** The handle's accessible name, when the label is shortened for a row. */
  name?: string;
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
  const row = useContext(RowFields);
  return (
    <Field
      label={row ? label : `${label}: ${format(shown)}`}
      hint={hint}
      after={
        row && (
          <Typography.Text style={{ width: 48, flex: "none", textAlign: "right" }} data-testid="slider-value">
            {format(shown)}
          </Typography.Text>
        )
      }
    >
      <Slider
        ariaLabelForHandle={name}
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
export function MotionSettings({ values, onChange, disabled, bare }: Props) {
  return (
    <Group title="Hình ảnh" testId="motion-settings" bare={bare}>
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
    </Group>
  );
}

const labelOf = (list: { value: string; label: string }[], value: string) =>
  list.find((item) => item.value === value)?.label;

/** The "Hình ảnh" panel's line while closed: "Mờ dần, Zoom vào, Mạnh". */
export function motionSummary(values: Pick<VideoOptions, "transition" | "motion" | "zoom">): string {
  return [
    labelOf(TRANSITIONS, values.transition),
    labelOf(MOTIONS, values.motion),
    values.motion === "static" ? undefined : labelOf(ZOOMS, values.zoom),
  ]
    .filter(Boolean)
    .join(", ");
}

/** The "Chữ & phụ đề" panel's line while closed: the box style, the size and the captions. */
export function textSummary(values: SettingsValues, styleName: string): string {
  const size = labelOf(TEXT_SIZES, values.text_size ?? "large");
  const captions =
    values.captions === "off" || !values.voice_enabled
      ? "Phụ đề tắt"
      : `Phụ đề ${labelOf(CAPTIONS, values.captions)?.toLowerCase()}`;
  return [styleName, `Cỡ ${size?.toLowerCase()}`, captions].join(", ");
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
  compact,
}: {
  look: Look;
  onChange: (changes: Partial<Look>) => void;
  disabled?: boolean;
  /** The style tiles small, in one row that scrolls sideways. */
  compact?: boolean;
}) {
  const hasBox = look.text_style !== "none" && look.box_opacity !== "none";
  const problems = warnings(
    palette(look.text_style, look.text_color, look.box_color, look.accent_color, look.box_opacity),
    hasBox,
  );
  return (
    <>
      <Field label="Kiểu hộp chữ" hint="Kiểu dùng chung cả đội. Chỉnh màu bên dưới không làm đổi kiểu.">
        <TextStyleCards values={look} onChange={onChange} disabled={disabled} compact={compact} />
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
const TEXT_SIZES = [
  { value: "large", label: "Lớn" },
  { value: "medium", label: "Vừa" },
  { value: "small", label: "Nhỏ" },
];

/** "Cỡ chữ": the largest size that fits is used, down to the smallest of the preset; a smaller one fits more words. */
function SizeField({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: VideoOptions["text_size"] | undefined;
  disabled?: boolean;
  onChange: (size: VideoOptions["text_size"]) => void;
}) {
  return (
    <Field label={label} hint="Lớn như mẫu gốc; Vừa và Nhỏ cho hộp chữ gọn hơn và chứa được chữ dài hơn.">
      <Segmented
        aria-label={label}
        options={TEXT_SIZES}
        value={value ?? "large"}
        disabled={disabled}
        onChange={(size) => onChange(size as VideoOptions["text_size"])}
      />
    </Field>
  );
}

const TEXT_CASES = [
  { value: "keep", label: "Giữ nguyên như đã nhập" },
  { value: "upper", label: "Viết hoa toàn bộ" },
];

/** "Dạng chữ": the text drawn as typed, or every letter a capital (the original template); marked words keep their colour. */
function CaseField({
  label,
  hint,
  value,
  disabled,
  onChange,
}: {
  label: string;
  hint: string;
  value: VideoOptions["text_case"] | undefined;
  disabled?: boolean;
  onChange: (textCase: VideoOptions["text_case"]) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <Segmented
        aria-label={label}
        options={TEXT_CASES}
        value={value ?? "upper"}
        disabled={disabled}
        onChange={(textCase) => onChange(textCase as VideoOptions["text_case"])}
      />
    </Field>
  );
}

export function TextSettings({ values, onChange, disabled, bare }: Props) {
  const [target, setTarget] = useState<"scenes" | "title">("scenes");
  const title = titleLook(values);
  const followsScenes =
    (!values.title_text_style || values.title_text_style === "same") && values.title_style !== "yellow";
  return (
    <Group title="Chữ & phụ đề" testId="text-settings" bare={bare}>
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
            <LookControls look={sceneLook(values)} onChange={onChange} disabled={disabled} compact={bare} />
            <SizeField
              label="Cỡ chữ"
              value={values.text_size}
              disabled={disabled}
              onChange={(text_size) => onChange({ text_size })}
            />
            <CaseField
              label="Dạng chữ"
              hint="Áp dụng cho chữ các cảnh và lớp chữ trên cảnh."
              value={values.text_case}
              disabled={disabled}
              onChange={(text_case) => onChange({ text_case })}
            />
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
                compact={bare}
              />
            )}
            <SizeField
              label="Cỡ chữ tiêu đề"
              value={values.title_text_size}
              disabled={disabled}
              onChange={(title_text_size) => onChange({ title_text_size })}
            />
            <CaseField
              label="Dạng chữ tiêu đề"
              hint="Riêng cho cảnh tiêu đề, không theo các cảnh."
              value={values.title_text_case}
              disabled={disabled}
              onChange={(title_text_case) => onChange({ title_text_case })}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Tiêu đề cũng là ảnh thumbnail của video. Phụ đề không hiện trên cảnh tiêu đề.
            </Typography.Text>
          </>
        )}
      </Flex>
    </Group>
  );
}
