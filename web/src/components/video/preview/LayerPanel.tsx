"use client";

import { DeleteOutlined, FontSizeOutlined, PictureOutlined } from "@ant-design/icons";
import { Button, Divider, Flex, Input, InputNumber, Popconfirm, Segmented, Select, Slider, Typography } from "antd";
import { useState } from "react";
import { api, type SceneData, type SceneLayer, type VideoDetail } from "@/lib/api";
import {
  ANIMATIONS,
  HALF_HEIGHT_MAX,
  HALF_HEIGHT_MIN,
  SIZES,
  STICKERS,
  TEXT_STYLES,
  halfPlaces,
  isHalf,
  layerName,
} from "./layers";

const seconds = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
/** A layer's longest seconds (routes_layers.MAX_SECONDS): longer than any scene, so "to the end of its scene". */
const WHOLE_SCENE = 60;

/**
 * "Chữ & sticker" in the tools column: a new text layer, or one of the stickers (drawn by the render core), added to
 * the scene being shown at the playhead.
 */
export function LayerTools({
  scene,
  editable,
  onAdd,
  onSaved,
  onPick,
  backdrop = false,
}: {
  scene: SceneData | undefined;
  editable: boolean;
  /** "Video xuyên suốt": the half-frame photo is the scene's own photo, found with the scene's picture tools. */
  backdrop?: boolean;
  onAdd: (body: Record<string, unknown>) => void;
  /** Saves a change and shows the saved video (false when it failed, its error already shown). */
  onSaved: (call: () => Promise<VideoDetail>) => Promise<boolean>;
  onPick: (id: number) => void;
}) {
  const allowed = editable && scene !== undefined && !scene.is_title;
  // One photo layer per scene: an older video's "Ảnh món" or a half-frame photo.
  const hasPhoto = scene?.layers.some((layer) => layer.kind === "photo") ?? false;
  const insetAllowed = allowed && !hasPhoto;
  const [busy, setBusy] = useState(false);

  /** A half-frame photo showing the scene's photo, picked once added so it can be dragged at once. */
  async function addInset() {
    if (!scene) return;
    setBusy(true);
    await onSaved(async () => {
      const saved = await api<VideoDetail>("/layers/half-photo", "POST", { scene_id: scene.id, scene_photo: true });
      const added = [saved.title_scene, ...saved.scenes].find((item) => item?.id === scene.id)?.layers.find(isHalf);
      if (added) onPick(added.id);
      return saved;
    });
    setBusy(false);
  }

  return (
    <Flex vertical gap={12} data-testid="layer-tools">
      <Typography.Text strong>Chữ & sticker</Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {scene?.is_title
          ? "Cảnh tiêu đề là ảnh bìa của video, nên không thêm lớp. Chọn một cảnh khác."
          : "Thêm vào cảnh đang xem, từ chỗ đầu phát, hiện 2 giây. Kéo lớp trên điện thoại để đổi chỗ."}
      </Typography.Text>
      <Button icon={<FontSizeOutlined />} disabled={!allowed} onClick={() => onAdd({ kind: "text", text: "Chữ mới" })}>
        Thêm chữ
      </Button>
      <div className="preview-colors" role="group" aria-label="Sticker">
        {STICKERS.map((item) => (
          <button
            key={item.value}
            type="button"
            className="preview-color"
            aria-label={`Thêm sticker ${item.label}`}
            disabled={!allowed}
            onClick={() => onAdd({ kind: "sticker", sticker: item.value })}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- drawn by the api with the render core */}
            <img
              src={`/api/layers/stickers/${item.value}.png`}
              alt=""
              style={{ aspectRatio: "1", objectFit: "contain" }}
            />
            <span>{item.label}</span>
          </button>
        ))}
      </div>
      {backdrop && (
        // Only a "Video xuyên suốt" has one: the scene's dish photo across half the frame, found and edited with the
        // scene's picture tools in "Chỉnh cảnh" › "Ảnh chèn", as "Ảnh món" was.
        <>
          <Divider style={{ margin: "4px 0" }} />
          <Typography.Text strong>Ảnh chèn</Typography.Text>
          <Flex vertical gap={6} data-testid="half-photo-tools">
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {hasPhoto && !scene?.is_title
                ? "Cảnh này đã có ảnh chèn: kéo lên xuống trên điện thoại, tìm hay sửa ảnh ở “Chỉnh cảnh” › “Ảnh chèn”."
                : "Ảnh của cảnh, tràn ngang khung, cao khoảng 1/3, hiện cùng lời đọc đến hết cảnh. Tìm hay sửa ảnh ở “Chỉnh cảnh” › “Ảnh chèn”."}
            </Typography.Text>
            <Button
              icon={<PictureOutlined />}
              disabled={!insetAllowed || busy}
              loading={busy}
              onClick={() => void addInset()}
            >
              Thêm ảnh chèn
            </Button>
          </Flex>
        </>
      )}
    </Flex>
  );
}

/**
 * "Chữ & sticker" in "Chỉnh cảnh N": the scene's layers, the picked one open to change its text, look, entrance and
 * seconds, each change saved at once (and undone with Ctrl+Z), or removed.
 */
export function LayerList({
  scene,
  selected,
  editable,
  onSelect,
  onPatch,
  onRemove,
}: {
  scene: SceneData;
  selected: number | null;
  editable: boolean;
  onSelect: (id: number | null) => void;
  onPatch: (layer: SceneLayer, label: string, body: Record<string, unknown>) => void;
  onRemove: (layer: SceneLayer) => void;
}) {
  if (scene.layers.length === 0) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Cảnh chưa có lớp nào. Thêm chữ hoặc sticker ở “Chữ & sticker” bên trái.
      </Typography.Text>
    );
  }
  return (
    <Flex vertical gap={6} data-testid="layer-list">
      {scene.layers.map((layer) => (
        <LayerRow
          key={`${layer.id}-${layer.text}-${layer.start}-${layer.seconds}`}
          layer={layer}
          sceneSeconds={scene.fitted_seconds}
          open={selected === layer.id}
          editable={editable}
          onOpen={() => onSelect(selected === layer.id ? null : layer.id)}
          onPatch={(label, body) => onPatch(layer, label, body)}
          onRemove={() => onRemove(layer)}
        />
      ))}
    </Flex>
  );
}

function LayerRow({
  layer,
  sceneSeconds,
  open,
  editable,
  onOpen,
  onPatch,
  onRemove,
}: {
  layer: SceneLayer;
  sceneSeconds: number;
  open: boolean;
  editable: boolean;
  onOpen: () => void;
  onPatch: (label: string, body: Record<string, unknown>) => void;
  onRemove: () => void;
}) {
  const [text, setText] = useState(layer.text);
  const [start, setStart] = useState<number | null>(layer.start);
  const [length, setLength] = useState<number | null>(layer.seconds);
  const commit = (field: "start" | "seconds", value: number | null, saved: number) => {
    if (value !== null && value !== saved) onPatch("đổi giờ của lớp", { [field]: value });
  };
  const half = isHalf(layer);
  // The render stops every layer at its scene's end, so a layer lasting past it shows to the end.
  const toEnd = layer.start + layer.seconds >= sceneSeconds;
  const times = (
    <Flex gap={8} wrap>
      <InputNumber
        aria-label="Giây bắt đầu của lớp"
        size="small"
        min={0}
        max={Math.max(0, sceneSeconds - 0.3)}
        step={0.1}
        precision={1}
        value={start}
        disabled={!editable}
        onChange={setStart}
        onBlur={() => commit("start", start, layer.start)}
        onPressEnter={() => commit("start", start, layer.start)}
        prefix="từ"
        suffix="s"
        style={{ width: 100 }}
      />
      <InputNumber
        aria-label="Số giây của lớp"
        size="small"
        min={0.3}
        max={WHOLE_SCENE}
        step={0.1}
        precision={1}
        value={length}
        disabled={!editable}
        onChange={setLength}
        onBlur={() => commit("seconds", length, layer.seconds)}
        onPressEnter={() => commit("seconds", length, layer.seconds)}
        prefix="dài"
        suffix="s"
        style={{ width: 100 }}
      />
    </Flex>
  );
  return (
    <Flex
      vertical
      gap={8}
      data-testid="layer-row"
      style={{ border: `1px solid ${open ? "#c2410c" : "#e7e8ea"}`, borderRadius: 6, padding: "6px 8px" }}
    >
      <Flex
        role="button"
        tabIndex={0}
        aria-expanded={open}
        align="center"
        gap={8}
        style={{ cursor: "pointer" }}
        onClick={onOpen}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onOpen();
          }
        }}
      >
        <Typography.Text strong style={{ fontSize: 12, flex: "none" }}>
          {layer.kind === "text" ? "Chữ" : layer.kind === "photo" ? "Ảnh" : "Sticker"}
        </Typography.Text>
        <Typography.Text ellipsis style={{ flex: 1, minWidth: 0, fontSize: 12 }}>
          {layerName(layer)}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
          {seconds(layer.start)}–{toEnd ? "hết cảnh" : `${seconds(layer.start + layer.seconds)}s`}
        </Typography.Text>
      </Flex>
      {open && half && (
        <Flex vertical gap={8}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Tràn sát hai mép, không viền, mép giáp ảnh nền mờ dần. Kéo lên xuống trên điện thoại (hút vào mép trên,
            giữa, mép dưới) hoặc chọn nhanh:
          </Typography.Text>
          <Segmented
            size="small"
            aria-label="Vị trí ảnh chèn"
            // A place dragged in between matches none of the quick places.
            value={halfPlaces(layer.height).find((place) => place.y === layer.y)?.value ?? ""}
            disabled={!editable}
            options={halfPlaces(layer.height).map((place) => ({ value: place.value, label: place.label }))}
            onChange={(value) => {
              const chosen = halfPlaces(layer.height).find((place) => place.value === value);
              if (chosen) onPatch("đổi vị trí ảnh chèn", { y: chosen.y });
            }}
          />
          <Flex align="center" gap={8}>
            <Typography.Text style={{ fontSize: 12, flex: "none" }}>Cao</Typography.Text>
            <Slider
              style={{ flex: 1, margin: "0 6px" }}
              min={HALF_HEIGHT_MIN}
              max={HALF_HEIGHT_MAX}
              value={layer.height}
              disabled={!editable}
              tooltip={{ formatter: (value) => `${value}%` }}
              onChangeComplete={(value) => onPatch("đổi chiều cao ảnh chèn", { height: value })}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
              {layer.height}%
            </Typography.Text>
          </Flex>
          {times}
          <Flex gap={8} wrap>
            <Button
              size="small"
              disabled={!editable || (layer.start === 0 && toEnd)}
              onClick={() => onPatch("hiện ảnh cả cảnh", { start: 0, seconds: WHOLE_SCENE })}
            >
              Hiện cả cảnh
            </Button>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!editable} onClick={onRemove}>
              Xoá ảnh
            </Button>
          </Flex>
        </Flex>
      )}
      {open && !half && (
        <Flex vertical gap={8}>
          {layer.kind === "text" && (
            <Input.TextArea
              aria-label="Chữ của lớp"
              autoSize={{ minRows: 1, maxRows: 4 }}
              value={text}
              disabled={!editable}
              onChange={(event) => setText(event.target.value)}
              onBlur={() => {
                if (text.trim() && text !== layer.text) onPatch("sửa chữ của lớp", { text });
              }}
            />
          )}
          {layer.kind === "text" && (
            <Select
              aria-label="Kiểu chữ của lớp"
              size="small"
              value={layer.style}
              disabled={!editable}
              options={TEXT_STYLES}
              onChange={(style) => onPatch("đổi kiểu chữ", { style })}
            />
          )}
          <Segmented
            size="small"
            aria-label="Cỡ của lớp"
            value={layer.size}
            disabled={!editable}
            options={SIZES}
            onChange={(size) => onPatch("đổi cỡ lớp", { size })}
          />
          <Select
            aria-label="Hiệu ứng vào"
            size="small"
            value={layer.animation}
            disabled={!editable}
            options={ANIMATIONS}
            onChange={(animation) => onPatch("đổi hiệu ứng vào", { animation })}
          />
          {times}
          <Popconfirm
            title="Xoá lớp này?"
            okText="Xoá"
            cancelText="Huỷ"
            okButtonProps={{ danger: true }}
            disabled={!editable}
            onConfirm={onRemove}
          >
            <Button size="small" danger icon={<DeleteOutlined />} disabled={!editable}>
              Xoá lớp
            </Button>
          </Popconfirm>
        </Flex>
      )}
    </Flex>
  );
}
