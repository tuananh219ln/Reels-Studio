"use client";

import { useMe } from "@/components/MeContext";
import { api, errorMessage, formatDateTime, type VideoDetail } from "@/lib/api";
import { myPageOfGroup } from "@/lib/lastChoices";
import { myPages, NO_PAGE_OF_MINE } from "@/lib/myPages";
import { App, Button, Popconfirm } from "antd";
import { useState } from "react";

/** The same manual approval on a plan idea, a video list and the video itself. Read fresh before confirming. */
export default function ApproveVideoButton({
  videoId,
  onDone,
  testId,
}: {
  videoId: number;
  onDone: () => unknown | Promise<unknown>;
  testId?: string;
}) {
  const { me } = useMe();
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  const [prepared, setPrepared] = useState<{ when: string; fanpage: number; name: string } | null>(null);
  async function approve() {
    setBusy(true);
    try {
      const video = await api<VideoDetail>(`/videos/${videoId}`);
      const when = video.plan_idea?.suggested_post_at;
      const own = myPages(video.fanpages, me.id);
      const fanpage = myPageOfGroup(video, me.id) ?? (own.length === 1 ? own[0].id : null);
      if (!when) throw new Error("Video chưa có giờ đăng dự kiến trong kế hoạch");
      if (new Date(when).getTime() <= Date.now())
        throw new Error("Giờ dự kiến đã qua, hãy đổi giờ trong kế hoạch hoặc mở Đăng bài");
      if (!video.mp4 || video.mp4_outdated) throw new Error("Hãy render lại trước khi đăng");
      if (video.locked) throw new Error("Video đang có job chạy, hãy đợi xong rồi duyệt");
      if (fanpage === null) throw new Error(NO_PAGE_OF_MINE);
      if (video.posted_fanpage_ids.includes(fanpage))
        throw new Error("Bản MP4 này đang có trên Fanpage đó. Hãy render bản mới hoặc xóa bài cũ.");
      setPrepared({ when, fanpage, name: video.fanpages.find((page) => page.id === fanpage)?.name ?? "" });
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function send() {
    if (!prepared) return;
    try {
      await api(`/videos/${videoId}/publish`, "POST", {
        fanpage_id: prepared.fanpage,
        scheduled_at: prepared.when,
        auto_comment: true,
      });
      message.success(`Đã hẹn đăng lúc ${formatDateTime(prepared.when)}`);
      setPrepared(null);
      await onDone();
    } catch (err) {
      message.error(errorMessage(err));
      throw err;
    }
  }
  return (
    <Popconfirm
      open={prepared !== null}
      onOpenChange={(next) => {
        if (next) void approve();
        else setPrepared(null);
      }}
      title={prepared ? `Duyệt đăng lúc ${formatDateTime(prepared.when)}?` : "Duyệt đăng?"}
      description={prepared ? `Video sẽ tự đăng lên Facebook, Page “${prepared.name}”, vào giờ này.` : undefined}
      okText="Duyệt"
      cancelText="Huỷ"
      onConfirm={send}
    >
      <Button size="small" type="primary" loading={busy} data-testid={testId}>
        Duyệt
      </Button>
    </Popconfirm>
  );
}
