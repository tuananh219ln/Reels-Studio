"use client";

import { Alert, App, Card, Empty, Flex, Segmented, Statistic, Table, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateRevenue } from "@/lib/api";

const money = (value: number) => `${value.toLocaleString("vi-VN")}đ`;

/** The signed-in member's own Shopee orders, read by the worker once a day; nobody else sees them. */
export default function Revenue() {
  const { message } = App.useApp();
  const [days, setDays] = useState(30);
  const [data, setData] = useState<AffiliateRevenue | null>(null);

  useEffect(() => {
    let live = true;
    api<AffiliateRevenue>(`/affiliate-accounts/revenue?days=${days}`).then(
      (found) => live && setData(found),
      (err) => live && message.error(errorMessage(err)),
    );
    return () => {
      live = false;
    };
  }, [days, message]);

  if (data && data.accounts.length === 0) {
    return (
      <Empty
        description={
          <span>
            Chưa có tài khoản Shopee nào của bạn. Thêm ở{" "}
            <Link href="/settings/affiliate-accounts">Cấu hình › Tài khoản affiliate</Link>.
          </span>
        }
      />
    );
  }

  return (
    <Flex vertical gap={16}>
      <Flex wrap gap={12} justify="space-between" align="center">
        <Segmented
          aria-label="Khoảng thời gian"
          value={days}
          onChange={(value) => setDays(value as number)}
          options={[
            { value: 7, label: "7 ngày" },
            { value: 30, label: "30 ngày" },
            { value: 90, label: "90 ngày" },
          ]}
        />
      </Flex>
      {data?.accounts
        .filter((account) => account.report_error)
        .map((account) => (
          <Alert
            key={account.id}
            type="warning"
            showIcon
            title={`Chưa đọc được đơn của “${account.name}”: ${account.report_error}`}
          />
        ))}
      <Flex wrap gap={16}>
        <Card size="small" style={{ minWidth: 180 }}>
          <Statistic title="Đơn hàng" value={data?.orders ?? 0} loading={!data} />
        </Card>
        <Card size="small" style={{ minWidth: 180 }}>
          <Statistic title="Hoa hồng" value={data ? money(data.commission) : "0đ"} loading={!data} />
        </Card>
      </Flex>
      <Card styles={{ body: { padding: 0 } }}>
        <Table
          rowKey={(line) => `${line.video_id}-${line.fanpage}`}
          loading={!data}
          dataSource={data?.lines ?? []}
          pagination={false}
          scroll={{ x: 600 }}
          locale={{ emptyText: "Chưa có đơn nào trong khoảng này" }}
          columns={[
            {
              title: "Video",
              key: "video",
              render: (_, line) =>
                line.video_id ? (
                  <Link href={`/videos/${line.video_id}`}>{line.title}</Link>
                ) : (
                  <Typography.Text type="secondary">Không rõ video (link tạo ngoài app)</Typography.Text>
                ),
            },
            { title: "Fanpage", dataIndex: "fanpage", key: "fanpage", render: (name) => name ?? "—" },
            { title: "Đơn", dataIndex: "orders", key: "orders", width: 90 },
            { title: "Hoa hồng", key: "commission", width: 140, render: (_, line) => money(line.commission) },
          ]}
        />
      </Card>
      {data?.accounts.some((account) => account.report_read_at) && (
        <Typography.Text type="secondary">
          Đọc lần cuối:{" "}
          {data.accounts
            .filter((account) => account.report_read_at)
            .map((account) => `${account.name} ${formatDateTime(account.report_read_at!)}`)
            .join(", ")}
        </Typography.Text>
      )}
    </Flex>
  );
}
