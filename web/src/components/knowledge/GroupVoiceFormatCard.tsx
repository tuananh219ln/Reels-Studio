"use client";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Input, InputNumber, Radio, Select, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type KnowledgeTopic, type VoiceFormat, type VoiceRole, type VoiceRoleName } from "@/lib/api";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;
type Mode = "none" | VoiceFormat["mode"];

const ROLE_LABELS: Record<VoiceRoleName, string> = {
  all: "Cả video",
  op: "Mở đầu (OP)",
  comment: "Bình luận",
  cta: "Kêu gọi (CTA)",
};
const MULTI_ROLES: VoiceRoleName[] = ["op", "comment", "cta"];

/** A role as the form edits it: its voices in one list (one voice, or several read in turn). */
type RoleRow = { role: VoiceRoleName; source: VoiceRole["source"]; voices: string[]; volume?: number; note: string };

function rowsOf(format: VoiceFormat | Record<string, never>): RoleRow[] {
  return ((format as VoiceFormat).roles ?? []).map((role) => ({
    role: role.role,
    source: role.source,
    voices: role.voices ?? (role.voice ? [role.voice] : []),
    volume: role.volume,
    note: role.note ?? "",
  }));
}

function formatOf(
  mode: Mode,
  rows: RoleRow[],
  gemini: number | null,
  excited: string,
): VoiceFormat | Record<string, never> {
  if (mode === "none") {
    return {};
  }
  const roles: VoiceRole[] = rows.map((row) => {
    const role: VoiceRole = { role: mode === "single" ? "all" : row.role, source: row.source };
    if (row.source === "provider") {
      if (row.voices.length > 1) {
        role.voices = row.voices;
      } else if (row.voices.length === 1) {
        role.voice = row.voices[0];
      }
    }
    if (row.volume !== undefined && row.volume !== null) {
      role.volume = row.volume;
    }
    if (row.note.trim()) {
      role.note = row.note.trim();
    }
    return role;
  });
  const rules: VoiceFormat["rules"] = {};
  if (gemini !== null) {
    rules.max_gemini_scenes = gemini;
  }
  if (excited.trim()) {
    rules.excited_tag = excited.trim();
  }
  return { mode, roles, ...(Object.keys(rules).length ? { rules } : {}) };
}

/**
 * "Giọng đọc theo vai": which voice reads each role of the group's videos, whether it is a voice service or an MP3
 * uploaded per scene, and the group's rules. Only shown and read (by members and assistants over MCP): it sets no
 * scene's voice by itself.
 */
export default function GroupVoiceFormatCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const saved = topic.voice_format as VoiceFormat | Record<string, never>;
  const [mode, setMode] = useState<Mode>((saved as VoiceFormat).mode ?? "none");
  const [rows, setRows] = useState<RoleRow[]>(rowsOf(saved));
  const [gemini, setGemini] = useState<number | null>((saved as VoiceFormat).rules?.max_gemini_scenes ?? null);
  const [excited, setExcited] = useState((saved as VoiceFormat).rules?.excited_tag ?? "");
  const [busy, setBusy] = useState(false);
  const changed = JSON.stringify(formatOf(mode, rows, gemini, excited)) !== JSON.stringify(saved);

  function pickMode(next: Mode) {
    setMode(next);
    if (next === "single") {
      setRows([rows[0] ? { ...rows[0], role: "all" } : { role: "all", source: "provider", voices: [], note: "" }]);
    } else if (next === "multi") {
      setRows(
        rows.length && rows[0].role !== "all"
          ? rows
          : [{ role: "op", source: "provider", voices: rows[0]?.voices ?? [], note: rows[0]?.note ?? "" }],
      );
    }
  }

  function edit(index: number, changes: Partial<RoleRow>) {
    setRows(rows.map((row, at) => (at === index ? { ...row, ...changes } : row)));
  }

  async function save() {
    setBusy(true);
    try {
      const result = await update({ voice_format: formatOf(mode, rows, gemini, excited) });
      const format = result.voice_format as VoiceFormat | Record<string, never>;
      setMode((format as VoiceFormat).mode ?? "none");
      setRows(rowsOf(format));
      message.success("Đã lưu giọng đọc theo vai");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const unused = MULTI_ROLES.filter((role) => !rows.some((row) => row.role === role));
  return (
    <Card title="Giọng đọc theo vai" size="small" data-testid="group-voice-format">
      <Typography.Paragraph type="secondary">
        Ghi rõ vai nào đọc bằng giọng nào để người dựng và trợ lý (qua MCP) làm đúng, không tự chọn giọng khác. Phần này
        không tự đổi giọng của cảnh. Nguồn “File tải lên” là file MP3 tải cho từng cảnh (nút Tải giọng lên trên trang
        video). Mã giọng giống ô Giọng đọc: mã ElevenLabs, vieneu:Tên, gemini:Tên hoặc google:Tên.
      </Typography.Paragraph>
      <Radio.Group value={mode} onChange={(event) => pickMode(event.target.value)} style={{ marginBottom: 12 }}>
        <Radio.Button value="none">Chưa khai</Radio.Button>
        <Radio.Button value="single">Một giọng</Radio.Button>
        <Radio.Button value="multi">Nhiều giọng theo vai</Radio.Button>
      </Radio.Group>
      {mode !== "none" && (
        <Flex vertical gap={12}>
          {rows.map((row, index) => (
            <Flex key={index} vertical gap={6} style={{ borderTop: index ? "1px solid rgba(0,0,0,0.06)" : undefined }}>
              <Flex wrap gap={8} align="center">
                {mode === "multi" ? (
                  <Select
                    value={row.role}
                    style={{ width: 150 }}
                    options={MULTI_ROLES.filter((role) => role === row.role || unused.includes(role)).map((role) => ({
                      value: role,
                      label: ROLE_LABELS[role],
                    }))}
                    onChange={(role) => edit(index, { role })}
                  />
                ) : (
                  <Typography.Text strong>{ROLE_LABELS.all}</Typography.Text>
                )}
                <Select
                  value={row.source}
                  style={{ width: 160 }}
                  options={[
                    { value: "provider", label: "Dịch vụ đọc" },
                    { value: "custom", label: "File tải lên" },
                  ]}
                  onChange={(source) => edit(index, { source })}
                />
                <InputNumber
                  min={0}
                  max={100}
                  value={row.volume}
                  placeholder="Âm lượng"
                  addonAfter="%"
                  style={{ width: 130 }}
                  onChange={(volume) => edit(index, { volume: volume ?? undefined })}
                />
                {mode === "multi" && rows.length > 1 && (
                  <Button
                    icon={<DeleteOutlined />}
                    aria-label="Xoá vai"
                    onClick={() => setRows(rows.filter((_, at) => at !== index))}
                  />
                )}
              </Flex>
              {row.source === "provider" && (
                <Select
                  mode="tags"
                  aria-label="Mã giọng của vai"
                  value={row.voices}
                  maxCount={mode === "single" ? 1 : 10}
                  open={false}
                  placeholder={
                    mode === "single" ? "Mã giọng, ví dụ vieneu:Huyền My" : "Một hoặc nhiều mã giọng (đọc lần lượt)"
                  }
                  tokenSeparators={[","]}
                  onChange={(voices: string[]) => edit(index, { voices: voices.map((voice) => voice.trim()) })}
                />
              )}
              <Input
                value={row.note}
                maxLength={300}
                placeholder="Ghi chú, ví dụ: V1–V3 Chi, V4–V6 Adam"
                onChange={(event) => edit(index, { note: event.target.value })}
              />
            </Flex>
          ))}
          {mode === "multi" && unused.length > 0 && (
            <Button
              icon={<PlusOutlined />}
              onClick={() => setRows([...rows, { role: unused[0], source: "provider", voices: [], note: "" }])}
            >
              Thêm vai
            </Button>
          )}
          <Flex wrap gap={8} align="center">
            <Typography.Text>Tối đa cảnh Gemini mỗi video</Typography.Text>
            <InputNumber min={0} max={50} value={gemini} placeholder="Không giới hạn" onChange={setGemini} />
          </Flex>
          <Input
            value={excited}
            maxLength={300}
            placeholder="Luật thẻ [excited], ví dụ: chỉ ElevenLabs, 1 lần mỗi video"
            onChange={(event) => setExcited(event.target.value)}
          />
        </Flex>
      )}
      <Button type="primary" loading={busy} disabled={!changed} style={{ marginTop: 12 }} onClick={save}>
        Lưu vai đọc
      </Button>
    </Card>
  );
}
