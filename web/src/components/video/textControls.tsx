"use client";

import { ColorPicker, Flex, Tooltip, Typography } from "antd";
import { SWATCHES, toHex, type Drawn } from "./textPalette";

/** A small 9:16 sample of a text box over a food-coloured background. */
export function Sample({ drawn, scale = 1 }: { drawn: Drawn; scale?: number }) {
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
        paddingBottom: 18 * scale,
      }}
    >
      <span
        style={{
          background: drawn.box ?? "none",
          color: drawn.text,
          textShadow: stroke,
          fontWeight: 900,
          fontSize: 9 * scale,
          lineHeight: 1.2,
          padding: `${3 * scale}px ${5 * scale}px`,
          borderRadius: 3 * scale,
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
export function ColorChoice({
  name,
  value,
  onChange,
  disabled,
  allowAuto = true,
}: {
  name: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  allowAuto?: boolean;
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
      {allowAuto && (
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
      )}
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
