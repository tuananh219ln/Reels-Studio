"use client";

import { api, errorMessage, type JobRow } from "@/lib/api";
import { App, Button, Flex, Popconfirm } from "antd";
import { useState } from "react";

export default function JobActions({
  job,
  onDone,
}: {
  job: Pick<JobRow, "id" | "status" | "can_cancel">;
  onDone: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [busy, setBusy] = useState(false);
  async function run(action: "retry" | "cancel") {
    setBusy(true);
    try {
      await api(`/jobs/${job.id}/${action}`, "POST");
      await onDone();
      message.success(action === "retry" ? "Đã gửi thử lại job" : "Đã hủy job");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Flex gap={4} onClick={(event) => event.stopPropagation()}>
      {job.status === "failed" && (
        <Popconfirm
          title="Thử lại job này?"
          description="Job sẽ chạy lại qua worker; các dịch vụ AI có thể phát sinh chi phí."
          okText="Thử lại"
          cancelText="Huỷ"
          onConfirm={() => run("retry")}
        >
          <Button size="small" loading={busy}>
            Thử lại
          </Button>
        </Popconfirm>
      )}
      {job.can_cancel && (
        <Popconfirm title="Hủy job đang chờ?" okText="Hủy job" cancelText="Không" onConfirm={() => run("cancel")}>
          <Button size="small" loading={busy}>
            Hủy job
          </Button>
        </Popconfirm>
      )}
    </Flex>
  );
}
