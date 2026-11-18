"use client";

import { api, errorMessage, type Article, type PinnedComment } from "@/lib/api";
import { HolderOutlined, ReloadOutlined, RobotOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Flex, Input, Radio, Switch, Tag, Typography } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";

const COUNT = 5;

/** The 5 comments of the plan script the article was made from: edited, put in order (drag), the one to pin chosen,
 *  written again by the AI, and the switch that decides whether they go under the post. Shown only for an article
 *  made from a plan script (api slot_comments.py). */
export default function PinnedCommentsCard({
  article,
  disabled,
  onSaved,
  reload,
}: {
  article: Article;
  disabled: boolean;
  onSaved: (article: Article) => void;
  reload: () => Promise<void>;
}) {
  const { message } = App.useApp();
  const slot = article.plan_slot;
  const [items, setItems] = useState<PinnedComment[]>([]);
  const [pin, setPin] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const dragged = useRef<number | null>(null);
  const asked = useRef(false);
  const pending = slot?.comments_pending ?? false;
  const slotId = slot?.id ?? null;
  const serverKey = slot ? JSON.stringify([slot.pinned_comments, slot.pin_index]) : "";

  // What the server holds replaces the form while nothing is being typed.
  useEffect(() => {
    if (!slot || dirty) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the form follows the script as the server sends it, unless a member is typing
    setItems(slot.pinned_comments);
    setPin(slot.pin_index);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `serverKey` stands for the two fields read
  }, [serverKey, dirty]);

  // A job in the worker writes them: ask again until it is done.
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void reload(), 2500);
    return () => clearInterval(timer);
  }, [pending, reload]);

  const generate = useCallback(
    async (index?: number) => {
      if (slotId === null) return;
      try {
        await api(`/article-plans/slots/${slotId}/comments/generate`, "POST", { index: index ?? null });
        setDirty(false);
        await reload();
      } catch (err) {
        message.error(errorMessage(err));
      }
    },
    [slotId, reload, message],
  );

  // A script with no comments gets them written when the page opens (once).
  useEffect(() => {
    if (slot && slot.comments_count === 0 && !slot.comments_pending && !asked.current && !slot.comments_error) {
      asked.current = true;
      void generate();
    }
  }, [slot, generate]);

  if (!slot) return null;
  const labels = slot.type_labels;

  async function save() {
    setSaving(true);
    try {
      const filled = items.map((item, place) => ({ item, place })).filter(({ item }) => item.text.trim());
      const chosen = Math.max(
        0,
        filled.findIndex(({ place }) => place === pin),
      );
      await api(`/article-plans/slots/${slot!.id}/comments`, "PUT", {
        pinned_comments: filled.map(({ item }) => item),
        pin_index: chosen,
      });
      setDirty(false);
      await reload();
      message.success("Đã lưu bình luận ghim");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function change(place: number, text: string) {
    setDirty(true);
    setItems((list) => {
      const next = [...list];
      while (next.length <= place) next.push({ type: slot!.type_set[next.length] ?? null, text: "" });
      next[place] = { ...next[place], text };
      return next;
    });
  }

  function drop(to: number) {
    const from = dragged.current;
    dragged.current = null;
    if (from === null || from === to) return;
    setDirty(true);
    const list = Array.from({ length: COUNT }, (_, place) => items[place] ?? { type: null, text: "" });
    const [moved] = list.splice(from, 1);
    list.splice(to, 0, moved);
    // The pin follows its comment.
    setPin((current) => {
      if (current === from) return to;
      if (from < current && to >= current) return current - 1;
      if (from > current && to <= current) return current + 1;
      return current;
    });
    setItems(list);
  }

  const places = Array.from({ length: COUNT }, (_, place) => place);
  const locked = disabled || pending || saving;

  return (
    <Card
      size="small"
      title={`Bình luận ghim (${items.filter((item) => item.text.trim()).length}/${COUNT})`}
      data-testid="pinned-comments"
      extra={
        <Flex gap={8} align="center">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Đăng kèm bình luận
          </Typography.Text>
          <Switch
            aria-label="Đăng kèm bình luận"
            checked={article.post_comments_enabled}
            disabled={disabled}
            onChange={async (checked) => {
              try {
                onSaved(await api<Article>(`/articles/${article.id}`, "PATCH", { post_comments_enabled: checked }));
              } catch (err) {
                message.error(errorMessage(err));
              }
            }}
          />
        </Flex>
      }
    >
      <Flex vertical gap={10}>
        {pending && <Alert type="info" showIcon title="AI đang viết bình luận…" />}
        {slot.comments_error && !pending && <Alert type="error" showIcon title={slot.comments_error} />}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Bình luận được đăng dưới tên Page theo thứ tự này (kéo để đổi). Bình luận chọn ghim được đăng trước; Facebook
          không cho app ghim, nên bạn ghim tay trên Facebook rồi bấm “Đã ghim”.
        </Typography.Text>
        {places.map((place) => {
          const item = items[place];
          const type = item?.type ?? slot.type_set[place] ?? null;
          return (
            <Flex
              key={place}
              gap={8}
              align="start"
              draggable={!locked}
              onDragStart={() => (dragged.current = place)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => drop(place)}
              data-testid="pinned-comment-row"
            >
              <HolderOutlined style={{ marginTop: 8, cursor: locked ? "default" : "grab" }} aria-hidden />
              <Radio
                checked={pin === place}
                disabled={locked}
                aria-label={`Ghim bình luận ${place + 1}`}
                onChange={() => {
                  setPin(place);
                  setDirty(true);
                }}
                style={{ marginTop: 4 }}
              />
              <Flex vertical gap={4} style={{ flex: 1 }}>
                <Flex gap={6} align="center">
                  {type && <Tag style={{ marginInlineEnd: 0 }}>{labels[type] ?? type}</Tag>}
                  {pin === place && <Tag color="blue">Ghim</Tag>}
                </Flex>
                <Input.TextArea
                  aria-label={`Bình luận ${place + 1}`}
                  value={item?.text ?? ""}
                  disabled={locked}
                  maxLength={1000}
                  autoSize={{ minRows: 2, maxRows: 6 }}
                  onChange={(event) => change(place, event.target.value)}
                />
              </Flex>
              <Button
                aria-label={`Tạo lại bình luận ${place + 1} bằng AI`}
                icon={<ReloadOutlined />}
                disabled={locked || slot.comments_count < COUNT || dirty}
                onClick={() => void generate(place)}
              />
            </Flex>
          );
        })}
        <Flex gap={8} wrap>
          <Button type="primary" disabled={!dirty || locked} loading={saving} onClick={save}>
            Lưu bình luận
          </Button>
          <Button icon={<RobotOutlined />} disabled={locked} onClick={() => void generate()}>
            Tạo lại bằng AI
          </Button>
          {dirty && (
            <Button
              disabled={saving}
              onClick={() => {
                setDirty(false);
              }}
            >
              Bỏ thay đổi
            </Button>
          )}
        </Flex>
      </Flex>
    </Card>
  );
}
