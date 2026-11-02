"use client";

import { QuestionCircleOutlined } from "@ant-design/icons";
import { Button, Flex, Input, Tooltip, Typography } from "antd";
import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import { errorMessage, type VideoDetail } from "@/lib/api";

type Editor = {
  /** A job is running: the api refuses every change until it ends. */
  locked: boolean;
  /** The page is in "Xem" (view) mode: nothing can be changed until the member presses "Chỉnh sửa". */
  readOnly: boolean;
  /** A field whose last save was refused says so, so "Xong" can keep the page in edit mode. */
  reportFailed: (field: string, failed: boolean) => void;
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

/** Words as a viewer reads them: the `*` marking red words does not count. */
export function countWords(text: string): number {
  return text.replaceAll("*", "").split(/\s+/).filter(Boolean).length;
}

/** "N từ", in yellow outside the recommended range (a warning only: it never stops the save). */
function WordCount({ text, min, max }: { text: string; min?: number; max: number }) {
  const count = countWords(text);
  if (count === 0) {
    return null;
  }
  const outside = count > max || (min !== undefined && count < min);
  const range = min !== undefined ? `${min}–${max}` : `tối đa ${max}`;
  return (
    <Typography.Text
      type={outside ? "warning" : "secondary"}
      style={{ marginLeft: "auto", whiteSpace: "nowrap" }}
      data-testid="word-count"
    >
      {count} từ{outside ? ` · nên ${range} từ` : ""}
    </Typography.Text>
  );
}

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
  help,
  words,
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
  /** Shown from a "?" beside the label. */
  help?: string;
  /** The recommended number of words, counted under the field as it is typed. */
  words?: { min?: number; max: number };
}) {
  const editor = useEditor();
  const field = useId();
  const { reportFailed } = editor;
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

  // A field that goes away no longer holds "Xong" back.
  useEffect(() => () => reportFailed(field, false), [field, reportFailed]);

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
          editor.reportFailed(field, false);
        }
        editor.onSaved(video);
      } catch (err) {
        setStatus({ kind: "error", message: errorMessage(err) });
        editor.reportFailed(field, true);
      }
    });
    queue.current = run;
    editor.track(run);
  }

  // In view mode the text reads as plain text; a field still holding unsaved text keeps its box.
  const viewing = editor.readOnly && !unsaved;
  const common = {
    "aria-label": label,
    value: text,
    placeholder: viewing ? undefined : placeholder,
    // A field holding unsaved text stays editable while locked: leaving it tries the save, which the api
    // refuses with its reason, and the text stays for a later "Lưu lại".
    readOnly: (editor.locked || editor.readOnly) && !unsaved,
    variant: viewing ? ("borderless" as const) : undefined,
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
        {help && (
          <Tooltip title={help}>
            <QuestionCircleOutlined aria-label="Cách viết" style={{ marginLeft: 6, color: "#8c8c8c" }} />
          </Tooltip>
        )}
      </Typography.Text>
      {multiline ? (
        <Input.TextArea
          {...common}
          autoSize={{ minRows: viewing ? 1 : rows, maxRows: 12 }}
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
            {!editor.locked && !editor.readOnly && (
              <Button size="small" type="link" onClick={commit}>
                Lưu lại
              </Button>
            )}
          </>
        )}
        {status.kind !== "error" && hint && !viewing && <Typography.Text type="secondary">{hint}</Typography.Text>}
        {words && <WordCount text={text} {...words} />}
      </Flex>
    </div>
  );
}
