"use client";

import { Button, Checkbox, Flex, Input, Radio, Typography } from "antd";
import { useState } from "react";

/** What the title scene shows: its text as one plain line (api plain_title). */
export function plainTitle(text: string): string {
  return text.replaceAll("*", "").replace(/\s+/g, " ").trim();
}

/**
 * The title of a video, three ways: one of the script's suggestions, typed by hand (both written to the title scene's
 * text, the suggestions themselves untouched), or "Không dùng tiêu đề" (the text kept aside and given back when
 * unticked; the video can be approved without a title). A line says what the screen will show.
 */
export default function TitleChooser({
  text,
  options,
  noTitle,
  disabled,
  saveText,
  setNoTitle,
}: {
  text: string;
  options: string[];
  noTitle: boolean;
  disabled: boolean;
  saveText: (text: string) => void;
  setNoTitle: (value: boolean) => void;
}) {
  const [typed, setTyped] = useState(text);
  const shown = plainTitle(text);
  const changed = typed.trim() !== text.trim() && typed.trim() !== "";
  return (
    <Flex vertical gap={8}>
      {options.length > 0 && (
        <>
          <Typography.Text type="secondary">Chọn 1 tiêu đề gợi ý để chép vào chữ cảnh tiêu đề:</Typography.Text>
          <Radio.Group
            style={{ display: "flex", flexDirection: "column", gap: 6 }}
            value={noTitle ? -1 : options.indexOf(text)}
            disabled={disabled}
            onChange={(event) => {
              const picked = options[event.target.value as number];
              setTyped(picked);
              saveText(picked);
            }}
            options={options.map((option, index) => ({ value: index, label: option }))}
          />
        </>
      )}
      <Typography.Text type="secondary">Hoặc tự nhập:</Typography.Text>
      <Flex gap={8}>
        <Input
          aria-label="Tiêu đề tự nhập"
          value={typed}
          maxLength={500}
          disabled={disabled}
          placeholder="Gõ tiêu đề hiện trên màn hình"
          onChange={(event) => setTyped(event.target.value)}
          onPressEnter={() => changed && saveText(typed.trim())}
        />
        <Button disabled={disabled || !changed} onClick={() => saveText(typed.trim())}>
          Lưu
        </Button>
      </Flex>
      <Checkbox
        checked={noTitle}
        disabled={disabled}
        onChange={(event) => {
          setNoTitle(event.target.checked);
          if (event.target.checked) setTyped("");
        }}
      >
        Không dùng tiêu đề
      </Checkbox>
      <Typography.Text data-testid="title-preview" style={{ fontSize: 13 }}>
        {shown ? (
          <>
            Trên màn hình sẽ hiện: <Typography.Text strong>{shown}</Typography.Text>
          </>
        ) : noTitle ? (
          "Không có chữ tiêu đề (duyệt được không cần tiêu đề)"
        ) : (
          "Chưa có chữ tiêu đề"
        )}
      </Typography.Text>
    </Flex>
  );
}
