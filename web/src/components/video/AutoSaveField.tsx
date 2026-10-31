"use client";

import { Button, Flex, Input, Typography } from "antd";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { errorMessage, type VideoDetail } from "@/lib/api";

type Editor = {
  locked: boolean;
  /** Every save in flight, so "Render" can wait for the field being typed in. */
  track: (save: Promise<unknown>) => void;
  /** Leave the field being typed in and wait until every pending save has finished. */
  flush: () => Promise<void>;
  onSaved: (video: VideoDetail) => void;
};

export const EditorContext = createContext<Editor | null>(null);

export function useEditor() {
  const editor = useContext(EditorContext);
  if (!editor) {
    throw new Error("useEditor must be used inside the video editor");
  }
  return editor;
}

type Status = { kind: "idle" | "saving" | "saved" } | { kind: "error"; message: string };

/**
 * One field that saves itself when it loses focus. Only this field is sent, so teammates editing other
 * fields never overwrite each other. A refused save keeps what was typed so it can be saved again.
 */
export default function AutoSaveField({
  label,
  value,
  save,
  multiline = false,
  rows = 2,
  placeholder,
  hint,
  inputMode,
  width,
}: {
  label: string;
  value: string;
  save: (text: string) => Promise<VideoDetail>;
  multiline?: boolean;
  rows?: number;
  placeholder?: string;
  hint?: React.ReactNode;
  inputMode?: "decimal";
  width?: number;
}) {
  const editor = useEditor();
  const [text, setText] = useState(value);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const focused = useRef(false);
  const dirty = useRef(false);
  // The same as dirty, as state, for rendering: refs are read only in handlers and effects.
  const [unsaved, setUnsaved] = useState(false);
  const latest = useRef(value);
  // Saves of this field run one after another, so an older text can never land after a newer one.
  const queue = useRef<Promise<void>>(Promise.resolve());

  // Teammates' saves arrive through polling; never replace what is being typed or not yet saved.
  useEffect(() => {
    if (!focused.current && !dirty.current) {
      latest.current = value;
      setText(value);
    }
  }, [value]);

  function edit(next: string) {
    dirty.current = true;
    setUnsaved(true);
    latest.current = next;
    setText(next);
  }

  function commit() {
    if (!dirty.current) {
      return;
    }
    const run = queue.current.then(async () => {
      if (!dirty.current) {
        return;
      }
      const sent = latest.current;
      setStatus({ kind: "saving" });
      try {
        const video = await save(sent);
        // Text typed while this save was on its way is still unsaved: the next blur sends it.
        if (latest.current === sent) {
          dirty.current = false;
          setUnsaved(false);
          setStatus({ kind: "saved" });
        }
        editor.onSaved(video);
      } catch (err) {
        setStatus({ kind: "error", message: errorMessage(err) });
      }
    });
    queue.current = run;
    editor.track(run);
  }

  const common = {
    "aria-label": label,
    value: text,
    placeholder,
    // A field holding unsaved text stays editable while locked: leaving it tries the save, which the api
    // refuses with its reason, and the text stays for a later "Lưu lại".
    readOnly: editor.locked && !unsaved,
    onFocus: () => {
      focused.current = true;
    },
    onBlur: () => {
      focused.current = false;
      commit();
    },
  };

  return (
    <div>
      <Typography.Text strong style={{ display: "block", marginBottom: 4 }}>
        {label}
      </Typography.Text>
      {multiline ? (
        <Input.TextArea
          {...common}
          autoSize={{ minRows: rows, maxRows: 12 }}
          onChange={(event) => edit(event.target.value)}
        />
      ) : (
        <Input
          {...common}
          inputMode={inputMode}
          style={width ? { width } : undefined}
          onChange={(event) => edit(event.target.value)}
          onPressEnter={(event) => event.currentTarget.blur()}
        />
      )}
      <Flex gap={8} align="center" style={{ minHeight: 22 }}>
        {status.kind === "saving" && <Typography.Text type="secondary">Đang lưu…</Typography.Text>}
        {status.kind === "saved" && <Typography.Text type="success">Đã lưu</Typography.Text>}
        {status.kind === "error" && (
          <>
            <Typography.Text type="danger">{status.message}</Typography.Text>
            {!editor.locked && (
              <Button size="small" type="link" onClick={commit}>
                Lưu lại
              </Button>
            )}
          </>
        )}
        {status.kind !== "error" && hint && <Typography.Text type="secondary">{hint}</Typography.Text>}
      </Flex>
    </div>
  );
}
