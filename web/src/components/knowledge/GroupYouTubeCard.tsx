"use client";

import { App, Button, Card, Flex, Input, Typography } from "antd";
import { useState } from "react";
import { errorMessage, type KnowledgeTopic, type YouTubeMeta } from "@/lib/api";
import { useLeaveGuard } from "@/lib/unsaved";
import EditHistory from "@/components/EditHistory";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

type Draft = { hashtags: string; keywords: string; cta: string; disclaimer: string };

function toDraft(meta: YouTubeMeta): Draft {
  return {
    hashtags: meta.hashtags.join(" "),
    keywords: meta.keywords.join(", "),
    cta: meta.cta,
    disclaimer: meta.disclaimer,
  };
}

/**
 * "Mô tả YouTube": what the group's YouTube uploads carry instead of the Facebook caption (api youtube_meta.py). The
 * description is built at each upload from the caption as it is then: the caption without its trailing hashtags, the
 * Subscribe line, the disclaimer and the YouTube hashtags; the keywords go to the tags only.
 */
export default function GroupYouTubeCard({ topic, update }: { topic: KnowledgeTopic; update: Update }) {
  const { message } = App.useApp();
  const [saved, setSaved] = useState(() => toDraft(topic.youtube_meta));
  const [draft, setDraft] = useState(saved);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  useLeaveGuard(() => dirty);

  function set(field: keyof Draft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function save() {
    setBusy(true);
    try {
      const body = {
        hashtags: draft.hashtags.split(/[\s,]+/).filter(Boolean),
        keywords: draft.keywords
          .split(/[,\n]+/)
          .map((word) => word.trim())
          .filter(Boolean),
        cta: draft.cta,
        disclaimer: draft.disclaimer,
      };
      const next = toDraft((await update({ youtube_meta: body })).youtube_meta);
      setSaved(next);
      setDraft(next);
      message.success("Đã lưu mô tả YouTube");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Mô tả YouTube"
      size="small"
      extra={
        <EditHistory
          entityType="knowledge_topic"
          entityId={topic.id}
          field="youtube_meta"
          title="Mô tả YouTube"
          kind="value"
          show={(value) => (value ? "Đã đặt" : "Chưa đặt")}
          current={topic.youtube_meta_set ? "Đã đặt" : "Chưa đặt"}
        />
      }
    >
      <Flex vertical gap={12} data-testid="youtube-meta">
        <Typography.Text type="secondary">
          Mỗi lần tải lên YouTube, mô tả là caption hiện tại (bỏ hashtag cuối), rồi câu đăng ký, lưu ý và hashtag
          YouTube; từ khóa chỉ gửi làm thẻ. Caption và hashtag Facebook không đổi. Để trống hết: YouTube nhận caption và
          hashtag Facebook như trước. Video đã tải lên không đổi.
        </Typography.Text>
        <label>
          <Typography.Text strong>Hashtag YouTube</Typography.Text>
          <Input.TextArea
            aria-label="Hashtag YouTube"
            value={draft.hashtags}
            placeholder="#FoodDose #Shorts #HealthTips … (10–20 cái, cách nhau bằng dấu cách)"
            autoSize={{ minRows: 2, maxRows: 4 }}
            onChange={(event) => set("hashtags", event.target.value)}
          />
        </label>
        <label>
          <Typography.Text strong>Từ khóa (thẻ)</Typography.Text>
          <Input.TextArea
            aria-label="Từ khóa YouTube"
            value={draft.keywords}
            placeholder="food is medicine, healthy foods, … (cách nhau bằng dấu phẩy, cả bộ thẻ tối đa 500 ký tự)"
            autoSize={{ minRows: 2, maxRows: 4 }}
            onChange={(event) => set("keywords", event.target.value)}
          />
        </label>
        <label>
          <Typography.Text strong>Câu kêu gọi đăng ký</Typography.Text>
          <Input
            aria-label="Câu kêu gọi đăng ký"
            value={draft.cta}
            maxLength={500}
            placeholder="🔔 Subscribe to {channel} for daily health tips."
            onChange={(event) => set("cta", event.target.value)}
          />
          <Typography.Text type="secondary">{"{channel}"} được thay bằng tên kênh YouTube nhận video.</Typography.Text>
        </label>
        <label>
          <Typography.Text strong>Lưu ý (disclaimer)</Typography.Text>
          <Input.TextArea
            aria-label="Lưu ý YouTube"
            value={draft.disclaimer}
            maxLength={2000}
            placeholder="Để trống nếu nhóm không cần lưu ý"
            autoSize={{ minRows: 2, maxRows: 6 }}
            onChange={(event) => set("disclaimer", event.target.value)}
          />
        </label>
        <div>
          <Button type="primary" loading={busy} disabled={!dirty} onClick={save}>
            Lưu mô tả YouTube
          </Button>
        </div>
      </Flex>
    </Card>
  );
}
