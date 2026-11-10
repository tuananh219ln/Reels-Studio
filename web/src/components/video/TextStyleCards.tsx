"use client";

import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Popconfirm, Segmented, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, type TextBoxStyle, type VideoOptions } from "@/lib/api";
import { ColorChoice, Sample } from "./textControls";
import { OPACITIES, palette, warnings } from "./textPalette";
import { COLORS } from "@/app/theme";
import FormDrawer from "@/components/FormDrawer";

type Look = Pick<VideoOptions, "text_style" | "text_color" | "box_color" | "accent_color" | "box_opacity">;
type Draft = Omit<TextBoxStyle, "id">;

const URL = "/settings/text-styles";
const NEW_STYLE: Draft = {
  name: "",
  box_color: "#FFD60A",
  box_opacity: "solid",
  text_color: "#111111",
  accent_color: "auto",
};
const COPIED = ["box_color", "text_color", "accent_color", "box_opacity"] as const;

/** The options a video copies from a team style; later edits to the style leave the video alone. */
export function styleLook(style: TextBoxStyle): Look {
  return { text_style: "box", ...Object.fromEntries(COPIED.map((name) => [name, style[name]])) } as Look;
}

const isChosen = (style: TextBoxStyle, values: Look) =>
  values.text_style === "box" && COPIED.every((name) => values[name] === style[name]);

function useTextStyles() {
  const [styles, setStyles] = useState<TextBoxStyle[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    api<TextBoxStyle[]>(URL)
      .then((list) => {
        setStyles(list);
        setError(null);
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);
  useEffect(reload, [reload]);
  return { styles, error, reload };
}

// Every tile is the same width, with its preview on top and a one-line name under it, so the row lines up.
const CARD_WIDTH = 72;

const cardStyle = (checked: boolean, disabled?: boolean) => ({
  width: CARD_WIDTH,
  padding: 3,
  border: `2px solid ${checked ? COLORS.primary : "transparent"}`,
  borderRadius: 10,
  background: "none",
  cursor: disabled ? "not-allowed" : "pointer",
  display: "flex",
  flexDirection: "column" as const,
  alignItems: "stretch",
  justifyContent: "flex-start",
  gap: 4,
});

/** The name under a tile: one line, cut with "…", whole in the tooltip. */
function CardName({ children }: { children: string }) {
  return (
    <Typography.Text ellipsis={{ tooltip: children }} style={{ fontSize: 12, display: "block", textAlign: "center" }}>
      {children}
    </Typography.Text>
  );
}

/** Create or edit one team style, with a live sample and the readability warnings. */
function StyleEditor({
  editing,
  onClose,
  onSaved,
}: {
  editing: TextBoxStyle | "new";
  onClose: () => void;
  onSaved: (style: TextBoxStyle) => void;
}) {
  // Mounted afresh for each style opened (see the key below), so the draft starts from it.
  const [draft, setDraft] = useState<Draft>(editing === "new" ? NEW_STYLE : editing);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = (changes: Partial<Draft>) => setDraft((current) => ({ ...current, ...changes }));
  const drawn = palette("box", draft.text_color, draft.box_color, draft.accent_color, draft.box_opacity);
  const outlined = draft.box_opacity === "none";
  const problems = warnings(drawn, !outlined);

  async function save() {
    setSaving(true);
    try {
      const body = { ...draft, name: draft.name.trim() };
      const saved =
        editing === "new"
          ? await api<TextBoxStyle>(URL, "POST", body)
          : await api<TextBoxStyle>(`${URL}/${editing.id}`, "PUT", body);
      onSaved(saved);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <FormDrawer
      open
      title={editing === "new" ? "Thêm kiểu hộp chữ" : "Sửa kiểu hộp chữ"}
      okText={editing === "new" ? "Thêm kiểu" : "Lưu"}
      cancelText="Huỷ"
      confirmLoading={saving}
      okButtonProps={{ disabled: !draft.name.trim() }}
      onOk={save}
      onClose={onClose}
      destroyOnHidden
    >
      <Flex gap={20} align="flex-start" wrap>
        <div style={{ width: 120 }}>
          <Sample drawn={drawn} scale={1.8} />
        </div>
        <Flex vertical gap={12} style={{ flex: 1, minWidth: 260 }}>
          <div>
            <Typography.Text strong>Tên kiểu</Typography.Text>
            <Input
              aria-label="Tên kiểu"
              placeholder="VD: Xanh navy…"
              maxLength={40}
              value={draft.name}
              onChange={(event) => set({ name: event.target.value })}
            />
          </div>
          <div>
            <Typography.Text strong>{outlined ? "Màu viền chữ" : "Màu nền hộp"}</Typography.Text>
            <ColorChoice
              name="Kiểu nền"
              allowAuto={false}
              value={draft.box_color}
              onChange={(box_color) => set({ box_color })}
            />
          </div>
          <div>
            <Typography.Text strong style={{ display: "block" }}>
              Độ trong của hộp
            </Typography.Text>
            <Segmented
              aria-label="Độ trong của kiểu"
              style={{ maxWidth: "100%", overflowX: "auto" }}
              options={OPACITIES.map(({ value, label }) => ({ value, label }))}
              value={draft.box_opacity}
              onChange={(box_opacity) => set({ box_opacity: box_opacity as Draft["box_opacity"] })}
            />
          </div>
          <div>
            <Typography.Text strong>Màu chữ</Typography.Text>
            <ColorChoice
              name="Kiểu chữ"
              allowAuto={false}
              value={draft.text_color}
              onChange={(text_color) => set({ text_color })}
            />
          </div>
          <div>
            <Typography.Text strong>Màu chữ đánh dấu</Typography.Text>
            <ColorChoice
              name="Kiểu đánh dấu"
              value={draft.accent_color}
              onChange={(accent_color) => set({ accent_color })}
            />
          </div>
          {problems.length > 0 && <Typography.Text type="warning">{problems.join(" ")}</Typography.Text>}
          {error && <Typography.Text type="danger">{error}</Typography.Text>}
        </Flex>
      </Flex>
    </FormDrawer>
  );
}

/** "Không hộp", the team's box styles and "+ Thêm kiểu"; picking a style copies its colours into the video. */
export function TextStyleCards({
  values,
  onChange,
  disabled,
}: {
  values: Look;
  onChange: (changes: Partial<Look>) => void;
  disabled?: boolean;
}) {
  const { message } = App.useApp();
  const { styles, error, reload } = useTextStyles();
  const [editing, setEditing] = useState<TextBoxStyle | "new" | null>(null);
  const noBox = values.text_style === "none";
  const chosen = styles?.find((style) => isChosen(style, values));

  async function remove(style: TextBoxStyle) {
    try {
      await api(`${URL}/${style.id}`, "DELETE");
      message.success(`Đã xoá kiểu “${style.name}”`);
      reload();
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Flex vertical gap={8}>
      <Flex wrap gap={8} align="flex-start" role="radiogroup" aria-label="Kiểu hộp chữ">
        <button
          type="button"
          role="radio"
          aria-checked={noBox}
          aria-label="Kiểu Không hộp"
          disabled={disabled}
          // No box brings its own outline; the text colours stay.
          onClick={() => onChange({ text_style: "none", box_color: "auto", box_opacity: "auto" })}
          style={cardStyle(noBox, disabled)}
        >
          <Sample drawn={palette("none", values.text_color, "auto", values.accent_color)} />
          <CardName>Không hộp</CardName>
        </button>
        {styles?.map((style) => {
          const checked = style === chosen;
          return (
            <button
              key={style.id}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-label={`Kiểu ${style.name}`}
              disabled={disabled}
              onClick={() => onChange(styleLook(style))}
              style={cardStyle(checked, disabled)}
            >
              <Sample
                drawn={palette("box", style.text_color, style.box_color, style.accent_color, style.box_opacity)}
              />
              <CardName>{style.name}</CardName>
            </button>
          );
        })}
        <button
          type="button"
          aria-label="Thêm kiểu"
          disabled={disabled}
          onClick={() => setEditing("new")}
          style={cardStyle(false, disabled)}
        >
          <div
            style={{
              aspectRatio: "9 / 16",
              borderRadius: 6,
              border: `2px dashed ${COLORS.border}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: COLORS.textSecondary,
              fontSize: 18,
            }}
          >
            <PlusOutlined />
          </div>
          <CardName>Thêm kiểu</CardName>
        </button>
      </Flex>
      {error && <Typography.Text type="danger">{error}</Typography.Text>}
      {chosen && (
        <Flex gap={4} align="center" wrap>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Kiểu chung của đội: “{chosen.name}”
          </Typography.Text>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => setEditing(chosen)}>
            Sửa kiểu
          </Button>
          <Popconfirm
            title={`Xoá kiểu “${chosen.name}”?`}
            description="Video đã dùng kiểu này vẫn giữ màu của nó."
            okText="Xoá"
            cancelText="Huỷ"
            onConfirm={() => remove(chosen)}
          >
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>
              Xoá kiểu
            </Button>
          </Popconfirm>
        </Flex>
      )}
      {editing && (
        <StyleEditor
          key={editing === "new" ? "new" : editing.id}
          editing={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            const added = editing === "new";
            setEditing(null);
            reload();
            message.success(added ? `Đã thêm kiểu “${saved.name}”` : `Đã lưu kiểu “${saved.name}”`);
            // A new style is picked at once; an edited one is picked again with its new colours.
            if (added || (chosen && chosen.id === saved.id)) {
              onChange(styleLook(saved));
            }
          }}
        />
      )}
    </Flex>
  );
}
