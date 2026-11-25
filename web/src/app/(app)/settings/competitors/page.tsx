"use client";

import { App, Button, Card, Flex, Form, InputNumber, Skeleton, Typography } from "antd";
import { useEffect, useState } from "react";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { api, errorMessage } from "@/lib/api";

type Rule = { min_hits: number; min_views: number };

/** Cài đặt › Phân tích đối thủ: when a competitor's channel is "big" and keeps only its best videos
 * (api competitors.threshold_settings). */
export default function CompetitorSettingsPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<Rule>();
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<Rule>("/competitors/settings").then(
      (rule) => {
        form.setFieldsValue(rule);
        setLoaded(true);
      },
      (err) => message.error(errorMessage(err)),
    );
  }, [form, message]);

  async function save(values: Rule) {
    setSaving(true);
    try {
      form.setFieldsValue(await api<Rule>("/competitors/settings", "PUT", values));
      message.success("Đã lưu ngưỡng kênh lớn");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <SettingsHeader
        title="Phân tích đối thủ"
        description="Một kênh đối thủ đủ lớn thì chỉ giữ các video nhiều view nhất trong danh sách; số liệu tổng (tổng view, trung vị, phân bổ) vẫn tính trên mọi video đã đọc."
      />
      <Card size="small" style={{ maxWidth: 560 }}>
        {!loaded ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : (
          <Form form={form} layout="vertical" onFinish={save}>
            <Form.Item
              label="Số video đạt ngưỡng để coi là kênh lớn"
              name="min_hits"
              rules={[{ required: true, message: "Nhập số video từ 1 đến 100" }]}
            >
              <InputNumber min={1} max={100} precision={0} inputMode="numeric" style={{ width: 160 }} />
            </Form.Item>
            <Form.Item
              label="Ngưỡng view"
              name="min_views"
              extra="Kênh lớn chỉ giữ video từ ngưỡng này trở lên. Ví dụ: 100000 là 100K view."
              rules={[{ required: true, message: "Nhập số view từ 1.000 đến 100.000.000" }]}
            >
              <InputNumber
                min={1_000}
                max={100_000_000}
                step={10_000}
                precision={0}
                inputMode="numeric"
                style={{ width: 160 }}
              />
            </Form.Item>
            <Flex gap={12} align="center" wrap>
              <Button type="primary" htmlType="submit" loading={saving}>
                Lưu ngưỡng
              </Button>
              <Typography.Text type="secondary">
                Áp dụng từ lượt quét kết thúc sau này; video đã bị bỏ không đọc lại.
              </Typography.Text>
            </Flex>
          </Form>
        )}
      </Card>
    </>
  );
}
