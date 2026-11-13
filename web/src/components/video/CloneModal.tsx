"use client";
import FormDrawer from "@/components/FormDrawer";
import { api, errorMessage, type VideoDetail } from "@/lib/api";
import { App, Input, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/** What "Tạo bản TikTok" asks the clone for, filled in for the member to change: a different file and a different
 * hook from the Facebook reel, so neither platform sees a copy (docs/specs/multi-platform/plan.md). */
const TIKTOK_REQUEST =
  "Viết lại cho TikTok: mở đầu bằng một câu hỏi khơi bình luận, caption ngắn, ít hashtag, đổi 1–2 cảnh và ảnh khác bản Facebook";
/** What "Nhân bản cho Page khác" on "Bài đăng" asks for: a real variant, never the same file on a second Page. */
const PAGE_REQUEST = "Viết biến thể cho Page khác: đổi câu mở đầu, đổi 1–2 cảnh và ảnh, giữ chủ đề";

/** "same": "Nhân bản" with an empty request; "page": a variant for another Page; "tiktok": the TikTok version. */
export type CloneTarget = "same" | "page" | "tiktok";

/** "Nhân bản": the team's LLM writes a new draft from this video as it is now, changed as the member asks.
 * "Tạo bản TikTok" is the same clone, made as the TikTok version of this video. */
export default function CloneModal({
  videoId,
  target,
  onClose,
}: {
  videoId: number;
  target: CloneTarget | null;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const router = useRouter();
  const [request, setRequest] = useState("");
  const [busy, setBusy] = useState(false);
  const open = target !== null;
  const tiktok = target === "tiktok";

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- a suggested request is prefilled each time it opens
    if (target === "tiktok" || target === "page") setRequest(target === "tiktok" ? TIKTOK_REQUEST : PAGE_REQUEST);
  }, [target]);

  async function submit() {
    setBusy(true);
    try {
      const draft = await api<VideoDetail>(`/videos/${videoId}/clone`, "POST", {
        request,
        ...(tiktok ? { platform: "tiktok" } : {}),
      });
      message.success(tiktok ? "Đã tạo bản TikTok" : "Đã tạo bản nháp nhân bản");
      onClose();
      router.push(`/videos/${draft.id}`);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={tiktok ? "Tạo bản TikTok" : "Nhân bản video"}
      open={open}
      onClose={onClose}
      onOk={submit}
      okText={tiktok ? "Tạo bản TikTok" : "Tạo bản nhân bản"}
      cancelText="Huỷ"
      okButtonProps={{ disabled: !request.trim() }}
      confirmLoading={busy}
      destroyOnHidden
      afterClose={() => setRequest("")}
    >
      <Typography.Paragraph type="secondary">
        AI giữ công thức của video này (đúng bản đang lưu) và viết một kịch bản mới theo yêu cầu đổi. Bản mới là một
        video nháp riêng, chưa có ảnh, có gợi ý nhạc mới, bản sao file MP3 và âm lượng; video này không bị khóa hay thay
        đổi.
      </Typography.Paragraph>
      <Typography.Text strong>Yêu cầu đổi</Typography.Text>
      <Input.TextArea
        aria-label="Yêu cầu đổi"
        value={request}
        placeholder="VD: đổi sang mốc 45 tuổi, tim mạch…"
        autoSize={{ minRows: 2, maxRows: 5 }}
        maxLength={300}
        onChange={(event) => setRequest(event.target.value)}
      />
    </FormDrawer>
  );
}
