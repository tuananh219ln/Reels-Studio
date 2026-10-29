"use client";

import { App, Button, Card, Flex, Input, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type Knowledge } from "@/lib/api";

export default function KnowledgePage() {
  const { message, modal } = App.useApp();
  const [saved, setSaved] = useState<Knowledge | null>(null);
  const [prompt, setPrompt] = useState("");
  const [banned, setBanned] = useState("");
  const [busy, setBusy] = useState<"prompt" | "banned" | null>(null);

  // Each box is saved on its own: a save refreshes only its own box, never unsaved text in the other.
  function show(data: Knowledge, box: "prompt" | "banned" | "both") {
    setSaved(data);
    if (box !== "banned") {
      setPrompt(data.script_prompt);
    }
    if (box !== "prompt") {
      setBanned(data.banned_words.join("\n"));
    }
  }

  useEffect(() => {
    api<Knowledge>("/knowledge")
      .then((data) => show(data, "both"))
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  async function savePrompt(value: string) {
    setBusy("prompt");
    try {
      show(await api<Knowledge>("/knowledge/script-prompt", "PUT", { value }), "prompt");
      message.success("Đã lưu prompt viết kịch bản");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function saveBanned() {
    setBusy("banned");
    try {
      const words = banned.split("\n").map((word) => word.trim()).filter(Boolean);
      show(await api<Knowledge>("/knowledge/banned-words", "PUT", { words }), "banned");
      message.success("Đã lưu danh sách từ cấm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  if (!saved) {
    return (
      <Flex justify="center" style={{ padding: 48 }}>
        <Spin />
      </Flex>
    );
  }

  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Kho kiến thức
      </Typography.Title>
      <Flex vertical gap={16}>
        <Card title="Prompt viết kịch bản" size="small">
          <Typography.Paragraph type="secondary">
            Chỗ điền <Typography.Text code>[Chủ đề]</Typography.Text> được thay bằng chủ đề của video; nếu xóa chỗ điền
            này, chủ đề được nối vào cuối prompt. Phần định dạng JSON đầu ra cố định trong app và không cần viết ở đây.
          </Typography.Paragraph>
          <Input.TextArea aria-label="Prompt viết kịch bản" value={prompt} autoSize={{ minRows: 10, maxRows: 30 }}
            onChange={(event) => setPrompt(event.target.value)} />
          <Flex wrap gap={8} style={{ marginTop: 12 }}>
            <Button type="primary" loading={busy === "prompt"} disabled={!prompt.trim()}
              onClick={() => savePrompt(prompt)}>
              Lưu prompt
            </Button>
            <Button
              disabled={busy !== null}
              onClick={() =>
                modal.confirm({
                  title: "Khôi phục prompt mặc định?",
                  content: "Prompt đang dùng sẽ được thay bằng bản mặc định.",
                  okText: "Khôi phục",
                  cancelText: "Huỷ",
                  onOk: () => savePrompt(saved.default_script_prompt),
                })
              }
            >
              Khôi phục mặc định
            </Button>
          </Flex>
        </Card>
        <Card title="Từ cấm" size="small">
          <Typography.Paragraph type="secondary">
            Mỗi dòng một từ. Tiêu đề, chữ cảnh, caption và bình luận ghim có từ cấm sẽ hiện cảnh báo vàng (không chặn
            render). Claude cũng được dặn tránh các từ này.
          </Typography.Paragraph>
          <Input.TextArea aria-label="Từ cấm" value={banned} autoSize={{ minRows: 5, maxRows: 20 }}
            onChange={(event) => setBanned(event.target.value)} />
          <Button type="primary" loading={busy === "banned"} style={{ marginTop: 12 }} onClick={saveBanned}>
            Lưu từ cấm
          </Button>
        </Card>
      </Flex>
    </>
  );
}
