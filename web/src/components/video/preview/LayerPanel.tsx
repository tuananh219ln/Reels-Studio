"use client";

import { DeleteOutlined, FontSizeOutlined } from "@ant-design/icons";
import { Button, Flex, Input, InputNumber, Popconfirm, Segmented, Select, Typography } from "antd";
import { useState } from "react";
import type { SceneData, SceneLayer } from "@/lib/api";
import { ANIMATIONS, SIZES, STICKERS, TEXT_STYLES, layerName } from "./layers";

const seconds = (value: number) => value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });

/**
 * "Chữ & sticker" in the tools column: a new text layer, or one of the stickers (drawn by the render core), added to
 * the scene being shown at the playhead.
 */
export function LayerTools({
  scene,
  editable,
  onAdd,
}: {
  scene: SceneData | undefined;
  editable: boolean;
  onAdd: (body: Record<string, unknown>) => void;
}) {
  const allowed = editable && scene !== undefined && !scene.is_title;
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
          {layer.kind === "text" ? "Chữ" : "Sticker"}
        </Typography.Text>
        <Typography.Text ellipsis style={{ flex: 1, minWidth: 0, fontSize: 12 }}>
          {layerName(layer)}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12, flex: "none" }}>
          {seconds(layer.start)}–{seconds(layer.start + layer.seconds)}s
        </Typography.Text>
      </Flex>
      {open && (
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
              max={60}
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
