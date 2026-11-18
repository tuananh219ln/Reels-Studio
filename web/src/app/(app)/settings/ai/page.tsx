"use client";

import { App, Collapse, Flex, Typography, type CollapseProps } from "antd";
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, type LlmSettings } from "@/lib/api";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { LastEdit, PageHistory, useLatestEdits } from "@/components/settings/SharedHistory";
import ScriptAiSettings, { aiOwners } from "@/components/settings/ScriptAiSettings";
import { AiImagesPanel, SOURCE_NAMES, StockPanel, useSources, VoicePanel } from "@/components/settings/SourceSettings";

const GROUPS = ["script", "voices", "images", "stock"] as const;
type Group = (typeof GROUPS)[number];
const OPEN_KEY = "settings-ai-open-groups";

/** Which groups the member left open: every one the first time; remembered in this browser only. */
function useOpenGroups(): [Group[], (keys: Group[]) => void] {
  const [open, setOpen] = useState<Group[]>([...GROUPS]);
  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(OPEN_KEY) ?? "null");
      if (Array.isArray(saved)) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- reads the browser's memory once, after mount
        setOpen(saved.filter((key): key is Group => (GROUPS as readonly string[]).includes(key)));
      }
    } catch {
      // No storage (private window): every group stays open.
    }
  }, []);
  const change = (keys: Group[]) => {
    setOpen(keys);
    try {
      window.localStorage.setItem(OPEN_KEY, JSON.stringify(keys));
    } catch {
      // Only a convenience.
    }
  };
  return [open, change];
}

function GroupLabel({ title, hint }: { title: string; hint: string }) {
  return (
    <Flex vertical gap={0}>
      <Typography.Text strong style={{ fontSize: 15 }}>
        {title}
      </Typography.Text>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {hint}
      </Typography.Text>
    </Flex>
  );
}

/** A group's "Lịch sử", in its header: a click on it opens the history, not the group. */
function GroupHistory({ group, ...props }: React.ComponentProps<typeof PageHistory> & { group: Group }) {
  return (
    <span data-testid={`history-${group}`} onClick={(event) => event.stopPropagation()}>
      <PageHistory {...props} />
    </span>
  );
}

/** "AI và nguồn tư liệu": everything the team's videos are made with, in groups that open and close: the AI that
 * writes scripts, the narration voices and their keys, AI photos, and the free stock libraries. */
export default function AiAndSourcesPage() {
  const { message } = App.useApp();
  const [llm, setLlm] = useState<LlmSettings | null>(null);
  const [open, setOpen] = useOpenGroups();
  const sources = useSources();
  // VieNeu's key is the second card of the AI settings' history.
  const aiLatest = useLatestEdits("settings_ai", llm);
  const owners = aiOwners(llm);

  const loadLlm = useCallback(async () => {
    try {
      setLlm(await api<LlmSettings>("/settings/llm"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void loadLlm();
  }, [loadLlm]);

  const items: CollapseProps["items"] = [
    {
      key: "script",
      label: <GroupLabel title="AI viết kịch bản" hint="Nhà cung cấp, API key và model viết kịch bản, nhân bản" />,
      extra: (
        <GroupHistory group="script" entityType="settings_ai" entityId={1} title="AI viết kịch bản" owners={owners} />
      ),
      children: <ScriptAiSettings settings={llm} onChange={setLlm} />,
    },
    {
      key: "voices",
      label: <GroupLabel title="Giọng đọc" hint="ElevenLabs, Gemini, VieNeu và key dự phòng của từng dịch vụ" />,
      children: (
        <VoicePanel
          state={sources}
          vieneuFooter={
            <LastEdit
              entry={aiLatest["2"]}
              entityType="settings_ai"
              entityId={2}
              title="Giọng đọc VieNeu"
              owners={owners}
            />
          }
        />
      ),
    },
    {
      key: "images",
      label: <GroupLabel title="Ảnh AI" hint="Nguồn mặc định, phong cách, key Cloudflare và Gemini" />,
      extra: (
        <GroupHistory
          group="images"
          entityType="settings_sources"
          entityId={2}
          title="Ảnh AI và giọng đọc"
          owners={SOURCE_NAMES}
        />
      ),
      children: <AiImagesPanel state={sources} />,
    },
    {
      key: "stock",
      label: <GroupLabel title="Kho ảnh và video miễn phí" hint="Pexels, Pixabay, Unsplash…, tự tìm ảnh và clip" />,
      extra: (
        <GroupHistory
          group="stock"
          entityType="settings_sources"
          entityId={1}
          title="Kho ảnh và video miễn phí"
          owners={SOURCE_NAMES}
        />
      ),
      children: <StockPanel state={sources} />,
    },
  ];

  return (
    <>
      <SettingsHeader
        title="AI và nguồn tư liệu"
        description="AI viết kịch bản, giọng đọc, ảnh AI và kho ảnh, video của cả nhóm. Bấm tên một nhóm để mở hoặc thu gọn. Key dán ở đây được mã hoá khi lưu, không bao giờ hiện lại, và được dùng thay key trong file .env của máy chủ."
      />
      <Collapse
        data-testid="settings-groups"
        style={{ background: "#fff" }}
        activeKey={open}
        onChange={(keys) => setOpen(keys as Group[])}
        items={items.map((item) => ({
          ...item,
          children: <div data-testid={`group-${String(item.key)}`}>{item.children}</div>,
        }))}
      />
    </>
  );
}
