"use client";

import { App, Button, Collapse, Flex, Select, Switch, Typography } from "antd";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import StatusText from "@/components/StatusText";
import { api, errorMessage, formatTime, type AffVideoPlan, type VideoDetail } from "@/lib/api";

const pre: React.CSSProperties = { whiteSpace: "pre-wrap", fontSize: 12, margin: 0 };

function minutes([low, high]: [number, number]) {
  const [a, b] = [low, high].map((seconds) => Math.round((seconds / 60) * 10) / 10);
  return a === b ? `${a}` : `${a}–${b}`;
}

/**
 * "Bình luận aff tự động" under "Bình luận thêm": the "Bộ bình luận" the Page would write under this video (api
 * aff_sets.py), per Page it is or may be posted on, with a choice of sets for this video alone or none at all.
 */
export default function AffComments({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const [plan, setPlan] = useState<AffVideoPlan | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<AffVideoPlan>(`/aff-sets/videos/${video.id}`).then(setPlan, () => undefined);
  }, [video.id]);
  // The plan reads the title and scenes: it follows them while the video is edited.
  const scenesKey = video.pinned_comment_text;
  useEffect(load, [load, scenesKey]);

  async function choose(off: boolean, setIds: number[] | null) {
    setBusy(true);
    try {
      setPlan(await api<AffVideoPlan>(`/aff-sets/videos/${video.id}`, "PUT", { off, set_ids: setIds }));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  // "Đăng aff ngay, bỏ chờ": the post's next comment goes up in the worker's next round, not after the Page's wait.
  async function writeNow(postId: number) {
    setBusy(true);
    try {
      setPlan(await api<AffVideoPlan>(`/aff-sets/posts/${postId}/now`, "POST"));
      message.success("Bình luận tiếp theo sẽ lên trong khoảng một phút");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (!plan || video.platform !== "facebook") return null;
  const own = plan.set_ids ?? [];
  return (
    <Flex vertical gap={4} data-testid="aff-comments">
      <Flex align="center" gap={8} wrap>
        <Typography.Text strong>Bình luận aff tự động</Typography.Text>
        <span style={{ marginLeft: "auto", fontSize: 12 }}>
          Không đăng cho video này{" "}
          <Switch
            size="small"
            checked={plan.off}
            loading={busy}
            aria-label="Không đăng bình luận aff cho video này"
            onChange={(off) => void choose(off, plan.set_ids)}
          />
        </span>
      </Flex>
      {plan.manual_comment ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Video đánh dấu “Đã dán link tay”: app không đăng bình luận nào.
        </Typography.Text>
      ) : plan.pages.length === 0 ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Chưa có Page nào đăng nhóm của video này.
        </Typography.Text>
      ) : (
        plan.pages.map((page) => {
          const mine = own.filter((id) => page.sets.some((one) => one.id === id));
          const others = own.filter((id) => !page.sets.some((one) => one.id === id));
          return (
            <Flex
              key={page.fanpage_id}
              vertical
              gap={4}
              style={{ padding: "6px 8px", background: "rgba(0,0,0,0.03)", borderRadius: 8 }}
            >
              <Flex align="center" gap={8} wrap>
                <Typography.Text>{page.name}</Typography.Text>
                {!page.enabled ? (
                  <StatusText tone="warning">Page đang tắt</StatusText>
                ) : plan.off ? (
                  <StatusText tone="warning">Tắt cho video này</StatusText>
                ) : (
                  <StatusText tone="success">
                    {mine.length ? "Chọn tay" : "Tự động"}: {page.planned.length} bộ
                  </StatusText>
                )}
                <Link href={`/affiliate?tab=sets&page=${page.fanpage_id}`} style={{ fontSize: 12, marginLeft: "auto" }}>
                  Bộ bình luận của Page
                </Link>
              </Flex>
              {page.enabled && !plan.off && (
                <>
                  <Select
                    mode="multiple"
                    size="small"
                    allowClear
                    maxCount={3}
                    disabled={busy}
                    placeholder="Tự động (app chọn theo chủ đề và xoay vòng)"
                    aria-label={`Bộ cho ${page.name}`}
                    value={mine}
                    options={page.sets.map((one) => ({ value: one.id, label: one.name, disabled: !one.enabled }))}
                    onChange={(next: number[]) => {
                      const ids = [...others, ...next];
                      void choose(plan.off, ids.length ? ids : null);
                    }}
                  />
                  {page.planned.length === 0 ? (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      Chưa có bộ nào dùng được (cần ít nhất 3 sản phẩm hợp lệ).
                    </Typography.Text>
                  ) : (
                    <Collapse
                      size="small"
                      items={page.planned.map((one, place) => ({
                        key: one.set_id,
                        label: `Aff ${place + 1} · ${one.set_name} · ${one.products} link · ${
                          place === 0
                            ? `${minutes(page.first_delay)} phút sau bình luận món ăn cuối`
                            : `${minutes(page.delay)} phút sau aff ${place}`
                        }`,
                        children: <pre style={pre}>{one.text}</pre>,
                      }))}
                    />
                  )}
                  {page.posts.map((row) => (
                    <Flex key={row.post_id} align="center" gap={8} wrap data-testid="aff-post">
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        Bài #{row.post_id}: đã đăng {row.count}/{row.total} bình luận aff
                        {row.next_at ? `, bình luận tiếp lúc ${formatTime(row.next_at)}` : ""}
                        {row.count > 0 ? " (bộ đã dùng giữ nguyên cho bài này)" : ""}.
                      </Typography.Text>
                      {row.error && <StatusText tone="warning">{row.error}</StatusText>}
                      {row.count < row.total && (
                        <Button
                          size="small"
                          loading={busy}
                          style={{ marginLeft: "auto" }}
                          onClick={() => void writeNow(row.post_id)}
                        >
                          Đăng aff ngay
                        </Button>
                      )}
                    </Flex>
                  ))}
                </>
              )}
            </Flex>
          );
        })
      )}
    </Flex>
  );
}
