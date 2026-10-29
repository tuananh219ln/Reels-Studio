"use client";

import { App, Button, Card, Flex, Input, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type Knowledge } from "@/lib/api";

export default function KnowledgePage() {
  const { message } = App.useApp();
  const [data, setData] = useState<Knowledge | null>(null);

  useEffect(() => {
    api<Knowledge>("/knowledge")
      .then(setData)
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  if (!data) {
    return (
      <Flex justify="center" style={{ padding: 48 }}>
        <Spin />
      </Flex>
    );
  }

  // Each box keeps its own text and saves on its own, so saving one never discards unsaved text in another.
  return (
    <>
      <Typography.Title level={2} style={{ marginTop: 0, fontWeight: 600 }}>
        Kho kiến thức
      </Typography.Title>
      <Flex vertical gap={16}>
        <PromptCard
          title="Prompt viết kịch bản"
          path="/knowledge/script-prompt"
          initial={data.script_prompt}
          fallback={data.default_script_prompt}
          help={
            <>
              Chỗ điền <Typography.Text code>[Chủ đề]</Typography.Text> được thay bằng chủ đề của video; nếu xóa chỗ
              điền này, chủ đề được nối vào cuối prompt.
            </>
          }
          pick={(saved) => saved.script_prompt}
        />
        <PromptCard
          title="Prompt nhân bản"
          path="/knowledge/clone-prompt"
          initial={data.clone_prompt}
          fallback={data.default_clone_prompt}
          help={
            <>
              Dùng khi bấm “Nhân bản”. Các chỗ điền <Typography.Text code>[tiêu đề]</Typography.Text>,{" "}
              <Typography.Text code>[chủ đề]</Typography.Text>,{" "}
              <Typography.Text code>[kịch bản đã sửa của video gốc]</Typography.Text> và{" "}
              <Typography.Text code>[yêu cầu đổi]</Typography.Text> được thay bằng dữ liệu của video gốc; chỗ điền nào
              bị xóa thì thông tin đó được nối vào cuối prompt.
            </>
          }
          pick={(saved) => saved.clone_prompt}
        />
        <BannedWordsCard initial={data.banned_words} />
      </Flex>
    </>
  );
}

function PromptCard({
  title,
  path,
  initial,
  fallback,
  help,
  pick,
}: {
  title: string;
  path: string;
  initial: string;
  fallback: string;
  help: React.ReactNode;
  pick: (saved: Knowledge) => string;
}) {
  const { message, modal } = App.useApp();
  const [value, setValue] = useState(initial);
  const [busy, setBusy] = useState(false);

  async function save(text: string) {
    setBusy(true);
    try {
      setValue(pick(await api<Knowledge>(path, "PUT", { value: text })));
      message.success(`Đã lưu ${title.toLowerCase()}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title={title} size="small">
      <Typography.Paragraph type="secondary">
        {help} Phần định dạng JSON đầu ra cố định trong app và không cần viết ở đây.
      </Typography.Paragraph>
      <Input.TextArea aria-label={title} value={value} autoSize={{ minRows: 8, maxRows: 30 }}
        onChange={(event) => setValue(event.target.value)} />
      <Flex wrap gap={8} style={{ marginTop: 12 }}>
        <Button type="primary" loading={busy} disabled={!value.trim()} onClick={() => save(value)}>
          Lưu
        </Button>
        <Button
          disabled={busy}
          onClick={() =>
            modal.confirm({
              title: `Khôi phục ${title.toLowerCase()} mặc định?`,
              content: "Prompt đang dùng sẽ được thay bằng bản mặc định.",
              okText: "Khôi phục",
              cancelText: "Huỷ",
              onOk: () => save(fallback),
            })
          }
        >
          Khôi phục mặc định
        </Button>
      </Flex>
    </Card>
  );
}

function BannedWordsCard({ initial }: { initial: string[] }) {
  const { message } = App.useApp();
  const [text, setText] = useState(initial.join("\n"));
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const words = text.split("\n").map((word) => word.trim()).filter(Boolean);
      setText((await api<Knowledge>("/knowledge/banned-words", "PUT", { words })).banned_words.join("\n"));
      message.success("Đã lưu danh sách từ cấm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Từ cấm" size="small">
      <Typography.Paragraph type="secondary">
        Mỗi dòng một từ. Tiêu đề, chữ cảnh, caption và bình luận ghim có từ cấm sẽ hiện cảnh báo vàng (không chặn
        render). Claude cũng được dặn tránh các từ này.
      </Typography.Paragraph>
      <Input.TextArea aria-label="Từ cấm" value={text} autoSize={{ minRows: 5, maxRows: 20 }}
        onChange={(event) => setText(event.target.value)} />
      <Button type="primary" loading={busy} style={{ marginTop: 12 }} onClick={save}>
        Lưu từ cấm
      </Button>
    </Card>
  );
}
