"use client";

import { Alert, App, Flex, Select, Typography } from "antd";
import { useEffect, useState } from "react";
import FormDrawer from "@/components/FormDrawer";
import { api, errorMessage, type Knowledge, type KnowledgeTopic, type VideoDetail } from "@/lib/api";
import { useMe } from "@/components/MeContext";

/** "Chuyển sang nhóm khác" on the video page, for the video's maker: the video goes to another topic group's list.
 * Nothing in the video changes; an idea of the old group's plan made from it is freed. */
export default function MoveGroupDrawer({
  video,
  open,
  onClose,
  onMoved,
}: {
  video: VideoDetail;
  open: boolean;
  onClose: () => void;
  onMoved: (video: VideoDetail) => void;
}) {
  const { message } = App.useApp();
  const { me } = useMe();
  // Not the maker of the video: the group's maker sends it back, only to a group of the video's maker.
  const sendBack = video.created_by_id !== me.id;
  const [groups, setGroups] = useState<KnowledgeTopic[] | null>(null);
  const [group, setGroup] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api<Knowledge>("/knowledge").then(
      (answer) => setGroups(answer.topics),
      (err) => {
        setGroups([]);
        message.error(errorMessage(err));
      },
    );
  }, [open, message]);

  function close() {
    setGroup(null);
    onClose();
  }

  async function move() {
    if (group === null) {
      message.error("Hãy chọn nhóm chủ đề");
      return;
    }
    setBusy(true);
    try {
      const moved = await api<VideoDetail>(`/videos/${video.id}/group`, "PUT", { knowledge_topic_id: group });
      message.success(`Đã chuyển video sang nhóm “${moved.knowledge_topic}”`);
      onMoved(moved);
      close();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={sendBack ? `Chuyển về nhóm của ${video.created_by}` : "Chuyển sang nhóm khác"}
      open={open}
      onClose={close}
      okText="Chuyển nhóm"
      onOk={move}
      confirmLoading={busy}
      okButtonProps={{ disabled: group === null }}
    >
      <Flex vertical gap={12}>
        <Typography.Text>
          Đang ở nhóm <Typography.Text strong>{video.knowledge_topic ?? "chưa có"}</Typography.Text>.
        </Typography.Text>
        <Select
          aria-label="Nhóm chủ đề mới"
          placeholder="Chọn nhóm chủ đề"
          notFoundContent={sendBack ? `${video.created_by} chưa có nhóm nào khác` : undefined}
          loading={groups === null}
          showSearch={{ optionFilterProp: "label" }}
          value={group}
          onChange={setGroup}
          options={(groups ?? [])
            .filter((topic) => topic.id !== video.knowledge_topic_id)
            .filter((topic) => !sendBack || topic.created_by_id === video.created_by_id)
            .map((topic) => ({ value: topic.id, label: topic.name }))}
        />
        <Alert
          type="info"
          showIcon
          title={
            video.plan_idea
              ? "Kịch bản, ảnh, MP4 và bài đã đăng giữ nguyên. Ý tưởng kế hoạch 30 ngày của nhóm cũ sẽ bỏ liên kết với video này và quay về “Ý tưởng”."
              : "Kịch bản, ảnh, MP4 và bài đã đăng giữ nguyên; chỉ đổi nhóm video thuộc về."
          }
        />
      </Flex>
    </FormDrawer>
  );
}
