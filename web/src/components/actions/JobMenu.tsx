"use client";

import { api, errorMessage, type JobRow } from "@/lib/api";
import { MoreOutlined } from "@ant-design/icons";
import { App, Button, Dropdown } from "antd";
import { useRouter } from "next/navigation";
import { useState } from "react";

/** The "⋮" menu at the end of a job's row: open what the job belongs to, retry a failed job, cancel a waiting one.
 * Retry and cancel ask first, as they did as buttons. The click does not reach the row, which opens on click. */
export default function JobMenu({
  job,
  href,
  openLabel,
  onDone,
}: {
  job: Pick<JobRow, "id" | "status" | "can_cancel">;
  href: string;
  openLabel: string;
  onDone: () => void | Promise<void>;
}) {
  const { message, modal } = App.useApp();
  const router = useRouter();
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

  const items = [
    { key: "open", label: openLabel, onClick: () => router.push(href) },
    ...(job.status === "failed"
      ? [
          {
            key: "retry",
            label: "Thử lại",
            onClick: () =>
              modal.confirm({
                title: "Thử lại job này?",
                content: "Job sẽ chạy lại qua worker; các dịch vụ AI có thể phát sinh chi phí.",
                okText: "Thử lại",
                cancelText: "Huỷ",
                onOk: () => run("retry"),
              }),
          },
        ]
      : []),
    ...(job.can_cancel
      ? [
          {
            key: "cancel",
            label: "Hủy job",
            danger: true,
            onClick: () =>
              modal.confirm({
                title: "Hủy job đang chờ?",
                okText: "Hủy job",
                cancelText: "Không",
                onOk: () => run("cancel"),
              }),
          },
        ]
      : []),
  ];

  return (
    <span onClick={(event) => event.stopPropagation()}>
      <Dropdown trigger={["click"]} placement="bottomRight" menu={{ items }}>
        <Button type="text" loading={busy} icon={<MoreOutlined />} aria-label={`Thao tác job #${job.id}`} />
      </Dropdown>
    </span>
  );
}
