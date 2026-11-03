"use client";

import { CopyOutlined, DeleteOutlined } from "@ant-design/icons";
import { App, Button, Card, Checkbox, Flex, Form, Input, Popconfirm, Select, Typography } from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateAccount, type VideoDetail } from "@/lib/api";
import { useEditor } from "./AutoSaveField";

/** What to do in TikTok's app, which the app cannot do for it: TikTok's API posting waits for issue #46. */
const CHECKLIST = [
  "Bật nhãn “Nội dung do AI tạo” (AIGC) khi đăng",
  "Gắn giỏ TikTok Shop với sản phẩm bên dưới, từ tài khoản TikTok của bạn",
  "Caption có câu “Tham khảo, không thay thế tư vấn bác sĩ”",
  "Chọn nhạc trong thư viện của TikTok, không mang nhạc từ nơi khác",
];

/** The TikTok version's posting kit: the MP4, the caption, the products for the cart, a checklist, then "Đã đăng
 * tay" records the post a member made in TikTok's app, on one of their own TikTok accounts. */
export default function TikTokCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const [accounts, setAccounts] = useState<AffiliateAccount[] | null>(null);
  const [products, setProducts] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm<{ account_id: number; url: string }>();

  useEffect(() => {
    let live = true;
    api<AffiliateAccount[]>("/affiliate-accounts").then(
      (found) => live && setAccounts(found.filter((account) => account.platform === "tiktok" && account.active)),
      () => live && setAccounts([]),
    );
    api<{ id: number; name: string }[]>("/affiliate-products?platform=tiktok_shop").then(
      (found) =>
        live &&
        setProducts(
          found.filter((product) => video.affiliate_product_ids.includes(product.id)).map((product) => product.name),
        ),
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [video.affiliate_product_ids]);

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      message.success(`Đã copy ${what}`);
    } catch {
      message.error("Trình duyệt không cho copy, hãy chọn chữ rồi copy tay");
    }
  }

  async function record(fields: { account_id: number; url: string }) {
    setBusy(true);
    try {
      onSaved(await api<VideoDetail>(`/tiktok/videos/${video.id}/posts`, "POST", fields));
      form.resetFields();
      message.success("Đã ghi bài TikTok");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(postId: number) {
    try {
      onSaved(await api<VideoDetail>(`/tiktok/posts/${postId}`, "DELETE"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <Card title="Đăng TikTok (đăng tay)" size="small" data-testid="tiktok-card">
      <Flex vertical gap={12}>
        <Typography.Text type="secondary">
          Tải MP4 về điện thoại rồi đăng trong app TikTok. App chưa tự đăng lên TikTok được.
        </Typography.Text>
        <Flex wrap gap={8}>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.post_text, "caption + hashtag")}>
            Copy caption + hashtag
          </Button>
          {video.affiliates.length > 0 && (
            <Button icon={<CopyOutlined />} onClick={() => copy(video.affiliates.join("\n"), "từ khoá sản phẩm")}>
              Copy từ khoá sản phẩm
            </Button>
          )}
        </Flex>
        <div>
          <Typography.Text strong>Sản phẩm gắn giỏ</Typography.Text>
          {products.length ? (
            <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
              {products.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : (
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              Chưa chọn sản phẩm TikTok Shop (ở thẻ Nội dung đăng). Có thể tìm trong mục “Thêm sản phẩm” của app TikTok
              theo từ khoá: {video.affiliates.join(", ") || "—"}.
            </Typography.Paragraph>
          )}
        </div>
        <Flex vertical gap={2}>
          <Typography.Text strong>Trước khi bấm đăng</Typography.Text>
          {CHECKLIST.map((item) => (
            <Checkbox key={item}>{item}</Checkbox>
          ))}
        </Flex>
        <Form form={form} layout="vertical" requiredMark={false} onFinish={record}>
          <Typography.Text strong>Đã đăng tay</Typography.Text>
          {accounts !== null && accounts.length === 0 ? (
            <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              Chưa có tài khoản TikTok của bạn. Thêm ở{" "}
              <Link href="/settings/affiliate-accounts">Cấu hình › Tài khoản affiliate</Link>.
            </Typography.Paragraph>
          ) : (
            <Flex wrap gap={8} align="flex-start" style={{ marginTop: 4 }}>
              <Form.Item name="account_id" rules={[{ required: true, message: "Chọn tài khoản" }]} noStyle>
                <Select
                  aria-label="Tài khoản TikTok"
                  placeholder="Tài khoản TikTok"
                  loading={accounts === null}
                  options={(accounts ?? []).map((account) => ({ value: account.id, label: account.name }))}
                  style={{ width: 200 }}
                />
              </Form.Item>
              <Form.Item name="url" rules={[{ required: true, whitespace: true, message: "Dán link bài" }]} noStyle>
                <Input
                  aria-label="Link bài TikTok"
                  placeholder="https://www.tiktok.com/@ten-kenh/video/…"
                  style={{ flex: "1 1 240px" }}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={busy}>
                Ghi bài đã đăng
              </Button>
            </Flex>
          )}
        </Form>
        {video.tiktok_posts.map((post) => (
          <Flex key={post.id} justify="space-between" align="center" gap={8} data-testid="tiktok-post">
            <Flex vertical gap={0} style={{ minWidth: 0 }}>
              <a href={post.url} target="_blank" rel="noreferrer">
                {post.account ?? "TikTok"}
              </a>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {formatDateTime(post.at)} · {post.created_by}
              </Typography.Text>
            </Flex>
            <Popconfirm
              title="Xoá bài này khỏi app?"
              description="Bài trên TikTok không bị đụng tới."
              okText="Xoá"
              cancelText="Huỷ"
              onConfirm={() => remove(post.id)}
            >
              <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="Xoá bài TikTok" />
            </Popconfirm>
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}
