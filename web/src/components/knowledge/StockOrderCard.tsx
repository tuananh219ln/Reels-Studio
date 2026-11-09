"use client";

import { ArrowDownOutlined, ArrowUpOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { api, errorMessage, type KnowledgeTopic, type StockSource } from "@/lib/api";

type Update = (body: Partial<KnowledgeTopic>) => Promise<KnowledgeTopic>;

/**
 * "Thứ tự nguồn ảnh": the order the group's videos ask the stock sources in ("Tự tìm ảnh" goes down it, the picker
 * and "Tìm ảnh" start on its first usable source). A new group takes the app's order; "Dùng thứ tự chung" goes back
 * to it, so later changes to the app's order reach the group again.
 */
export default function StockOrderCard({
  initial,
  custom: initialCustom,
  update,
}: {
  initial: string[];
  custom: boolean;
  update: Update;
}) {
  const { message } = App.useApp();
  const [order, setOrder] = useState(initial);
  const [custom, setCustom] = useState(initialCustom);
  const [sources, setSources] = useState<StockSource[]>([]);
  const [busy, setBusy] = useState(false);

  // Labels and whether each source can be used now (a key pasted, not turned off on Cài đặt › Nguồn tư liệu).
  useEffect(() => {
    let open = true;
    api<StockSource[]>("/stock/sources").then(
      (all) => open && setSources(all),
      () => undefined,
    );
    return () => {
      open = false;
    };
  }, []);

  const changed = order.join() !== initial.join();

  function move(index: number, by: number) {
    const next = [...order];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    setOrder(next);
  }

  async function save(body: string[]) {
    setBusy(true);
    try {
      const saved = await update({ stock_order: body });
      setOrder(saved.stock_order);
      setCustom(saved.stock_order_custom);
      message.success(body.length ? "Đã lưu thứ tự nguồn ảnh" : "Nhóm dùng lại thứ tự chung");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Thứ tự nguồn ảnh" size="small" data-testid="stock-order-card">
      <Typography.Paragraph type="secondary">
        Video của nhóm tìm ảnh kho theo thứ tự này: “Tự tìm ảnh” thử lần lượt từ trên xuống, hộp chọn ảnh và nút “Tìm
        ảnh” mở sẵn nguồn đầu tiên dùng được. Nhóm món Việt nên để Wikimedia lên đầu (tìm được tên món tiếng Việt).{" "}
        {custom ? "Nhóm đang dùng thứ tự riêng." : "Nhóm đang dùng thứ tự chung của app."}
      </Typography.Paragraph>
      <Flex vertical gap={6}>
        {order.map((id, index) => {
          const source = sources.find((item) => item.id === id);
          return (
            <Flex key={id} align="center" gap={8} data-testid="stock-order-item">
              <Typography.Text type="secondary" style={{ width: 20 }}>
                {index + 1}.
              </Typography.Text>
              <Typography.Text style={{ flex: 1, minWidth: 0 }}>{source?.label ?? id}</Typography.Text>
              {source && !source.available && <Tag>{source.missing_key ? "Chưa có key" : "Đang tắt"}</Tag>}
              <Button
                size="small"
                icon={<ArrowUpOutlined />}
                aria-label={`Đưa ${source?.label ?? id} lên`}
                disabled={busy || index === 0}
                onClick={() => move(index, -1)}
              />
              <Button
                size="small"
                icon={<ArrowDownOutlined />}
                aria-label={`Đưa ${source?.label ?? id} xuống`}
                disabled={busy || index === order.length - 1}
                onClick={() => move(index, 1)}
              />
            </Flex>
          );
        })}
      </Flex>
      <Flex gap={8} wrap style={{ marginTop: 12 }}>
        <Button type="primary" loading={busy} disabled={!changed} onClick={() => void save(order)}>
          Lưu thứ tự
        </Button>
        {custom && (
          <Button disabled={busy} onClick={() => void save([])}>
            Dùng thứ tự chung
          </Button>
        )}
      </Flex>
    </Card>
  );
}
