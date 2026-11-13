"use client";

import { CopyOutlined, DeleteOutlined, SendOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Flex,
  Form,
  Input,
  Popconfirm,
  Radio,
  Select,
  Tag,
  Typography,
} from "antd";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, errorMessage, formatDateTime, type AffiliateAccount, type TikTokPost, type VideoDetail } from "@/lib/api";
import { useMe } from "@/components/MeContext";
import { useEditor } from "./AutoSaveField";

/** TikTok's privacy levels; the job checks the one picked against what TikTok allows the account. */
const PRIVACY_LEVELS = [
  { value: "SELF_ONLY", label: "Chỉ mình tôi" },
  { value: "MUTUAL_FOLLOW_FRIENDS", label: "Bạn bè" },
  { value: "FOLLOWER_OF_CREATOR", label: "Người theo dõi" },
  { value: "PUBLIC_TO_EVERYONE", label: "Công khai" },
];

type PublishFields = { account_id: number; mode: "draft" | "direct"; privacy_level: string };

/** What to do in TikTok's app, which the app cannot do for it: TikTok's API cannot attach TikTok Shop's cart. */
const CHECKLIST = [
  "Bật nhãn “Nội dung do AI tạo” (AIGC) khi đăng",
  "Gắn giỏ TikTok Shop với sản phẩm bên dưới, từ tài khoản TikTok của bạn",
  "Caption có câu “Tham khảo, không thay thế tư vấn bác sĩ”",
  "Chọn nhạc trong thư viện của TikTok, không mang nhạc từ nơi khác",
];

/** The TikTok posting kit of any video (a TikTok version, or a Facebook video's own MP4): the caption, the products
 * for the cart, a checklist, then either
 * "Đăng lên TikTok" (sent through TikTok's API with the member's own connection: a draft to their TikTok inbox, or
 * posted directly) or "Đã đăng tay", which records a post made in TikTok's app, on one of their own accounts. */
export default function TikTokCard({ video }: { video: VideoDetail }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const [accounts, setAccounts] = useState<AffiliateAccount[] | null>(null);
  const [products, setProducts] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [sending, setSending] = useState(false);
  const [form] = Form.useForm<{ account_id: number; url: string }>();
  const [publishForm] = Form.useForm<PublishFields>();
  const mode = Form.useWatch("mode", publishForm) ?? "draft";
  const connected = (accounts ?? []).filter(
    (account) => account.tiktok_connection && !account.tiktok_connection.needs_reconnect,
  );

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

  async function publish(fields: PublishFields) {
    setSending(true);
    try {
      onSaved(
        await api<VideoDetail>(`/tiktok/videos/${video.id}/publish`, "POST", {
          account_id: fields.account_id,
          mode: fields.mode,
          privacy_level: fields.mode === "direct" ? fields.privacy_level : null,
        }),
      );
      message.success(fields.mode === "draft" ? "Đang gửi nháp lên TikTok" : "Đang đăng lên TikTok");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSending(false);
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
    <Card title="Đăng TikTok" size="small" data-testid="tiktok-card">
      <Flex vertical gap={12}>
        <Typography.Text type="secondary">
          Gửi video lên TikTok của bạn (Nháp: video vào hộp thư TikTok, bạn gắn giỏ + nhãn AI rồi bấm đăng trong app),
          hoặc tải MP4 về điện thoại rồi đăng tay.
        </Typography.Text>
        <Flex wrap gap={8}>
          <Button icon={<CopyOutlined />} onClick={() => copy(video.tiktok_caption, "caption + hashtag")}>
            Copy caption + hashtag
          </Button>
          {video.affiliates.length > 0 && (
            <Button icon={<CopyOutlined />} onClick={() => copy(video.affiliates.join("\n"), "từ khoá sản phẩm")}>
              Copy từ khoá sản phẩm
            </Button>
          )}
        </Flex>
        <div>
          <Typography.Text strong>Caption TikTok</Typography.Text>
          <Typography.Paragraph type="secondary" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {video.tiktok_caption}
          </Typography.Paragraph>
        </div>
        <div>
          <Typography.Text strong>Sản phẩm gắn giỏ</Typography.Text>
          {products.length ? (
            <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
              {products.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          ) : video.platform === "tiktok" ? (
            <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
              Chưa chọn sản phẩm TikTok Shop (ở thẻ Nội dung đăng). Có thể tìm trong mục “Thêm sản phẩm” của app TikTok
              theo từ khoá: {video.affiliates.join(", ") || "—"}.
            </Typography.Paragraph>
          ) : (
            // A Facebook video's MP4 on TikTok: its products are Shopee's, the cart is set in TikTok's app.
            <Typography.Paragraph type="secondary" style={{ margin: 0 }} data-testid="tiktok-from-facebook">
              Video Facebook dùng sản phẩm Shopee, nên giỏ TikTok Shop gắn trong app TikTok theo từ khoá:{" "}
              {video.affiliates.join(", ") || "—"}. Muốn kịch bản và sản phẩm riêng cho TikTok thì dùng “Tạo bản
              TikTok”.
            </Typography.Paragraph>
          )}
        </div>
        <Flex vertical gap={2}>
          <Typography.Text strong>Trước khi bấm đăng</Typography.Text>
          {CHECKLIST.map((item) => (
            <Checkbox key={item}>{item}</Checkbox>
          ))}
        </Flex>
        <Form
          form={publishForm}
          layout="vertical"
          requiredMark={false}
          initialValues={{ mode: "draft", privacy_level: "SELF_ONLY" }}
          onFinish={publish}
          data-testid="tiktok-publish"
        >
          <Typography.Text strong>Đăng lên TikTok</Typography.Text>
          {accounts !== null && connected.length === 0 ? (
            <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              Chưa có tài khoản TikTok nào đã kết nối. Bấm Kết nối TikTok ở{" "}
              <Link href="/settings/affiliate-accounts">Cài đặt › Tài khoản affiliate</Link>.
            </Typography.Paragraph>
          ) : (
            <Flex vertical gap={8} style={{ marginTop: 4 }}>
              <Flex wrap gap={8} align="center">
                <Form.Item name="account_id" rules={[{ required: true, message: "Chọn tài khoản" }]} noStyle>
                  <Select
                    aria-label="Tài khoản TikTok đã kết nối"
                    placeholder="Tài khoản TikTok"
                    loading={accounts === null}
                    options={connected.map((account) => ({
                      value: account.id,
                      label: `${account.name} (@${account.tiktok_connection?.username})`,
                    }))}
                    style={{ width: 240 }}
                  />
                </Form.Item>
                <Form.Item name="mode" noStyle>
                  <Radio.Group
                    optionType="button"
                    options={[
                      { value: "draft", label: "Nháp" },
                      { value: "direct", label: "Đăng thẳng" },
                    ]}
                  />
                </Form.Item>
              </Flex>
              {mode === "direct" && (
                <>
                  <Form.Item name="privacy_level" noStyle>
                    <Select aria-label="Mức riêng tư" options={PRIVACY_LEVELS} style={{ width: 240 }} />
                  </Form.Item>
                  <Alert
                    type="warning"
                    showIcon
                    title="App chưa qua duyệt TikTok: hiện chỉ đăng được ở chế độ riêng tư (Chỉ mình tôi) lên tài khoản đang để private"
                    description="Đăng thẳng không gắn được giỏ TikTok Shop; video được gắn nhãn “Nội dung do AI tạo”."
                  />
                </>
              )}
              <div>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SendOutlined />}
                  loading={sending}
                  disabled={!video.mp4 || video.locked}
                >
                  Đăng lên TikTok
                </Button>
              </div>
            </Flex>
          )}
        </Form>
        <Form form={form} layout="vertical" requiredMark={false} onFinish={record}>
          <Typography.Text strong>Đã đăng tay</Typography.Text>
          {accounts !== null && accounts.length === 0 ? (
            <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
              Chưa có tài khoản TikTok của bạn. Thêm ở{" "}
              <Link href="/settings/affiliate-accounts">Cài đặt › Tài khoản affiliate</Link>.
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
          <TikTokPostRow key={post.id} post={post} videoId={video.id} onRemove={() => remove(post.id)} />
        ))}
      </Flex>
    </Card>
  );
}

const MODE_LABELS = { draft: "Nháp TikTok", direct: "Đăng thẳng" } as const;
const STATUS_LABELS = { pending: "Đang gửi", published: null, cancelled: "Đã hủy" } as const;

/** One TikTok post: its account and link; one sent through TikTok's API also its way ("Nháp TikTok" / "Đăng thẳng"),
 * and, once on TikTok, a box where the member who sent it adds its link (TikTok's API does not give it). */
function TikTokPostRow({ post, videoId, onRemove }: { post: TikTokPost; videoId: number; onRemove: () => void }) {
  const { message } = App.useApp();
  const { onSaved } = useEditor();
  const { me } = useMe();
  const [url, setUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const status = STATUS_LABELS[post.status];

  async function addUrl() {
    setSaving(true);
    try {
      onSaved(await api<VideoDetail>(`/tiktok/posts/${post.id}/url`, "POST", { url }));
      setUrl("");
      message.success("Đã gắn link bài TikTok");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Flex vertical gap={4} data-testid="tiktok-post" data-video={videoId}>
      <Flex justify="space-between" align="center" gap={8}>
        <Flex vertical gap={0} style={{ minWidth: 0 }}>
          <Flex wrap gap={4} align="center">
            {post.url ? (
              <a href={post.url} target="_blank" rel="noreferrer">
                {post.account ?? "TikTok"}
              </a>
            ) : (
              <Typography.Text>{post.account ?? "TikTok"}</Typography.Text>
            )}
            {post.mode && <Tag color={post.mode === "draft" ? "blue" : "magenta"}>{MODE_LABELS[post.mode]}</Tag>}
            {status && <Tag>{status}</Tag>}
          </Flex>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {formatDateTime(post.at)}, {post.created_by}
          </Typography.Text>
        </Flex>
        <Popconfirm
          title="Xoá bài này khỏi app?"
          description="Bài trên TikTok không bị đụng tới."
          okText="Xoá"
          cancelText="Huỷ"
          onConfirm={onRemove}
        >
          <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="Xoá bài TikTok" />
        </Popconfirm>
      </Flex>
      {post.mode && post.status === "published" && !post.url && post.created_by_id === me.id && (
        <Flex gap={8}>
          <Input
            aria-label="Link bài TikTok đã đăng"
            placeholder="Dán link bài sau khi đăng: https://www.tiktok.com/@ten-kenh/video/…"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
          <Button onClick={addUrl} loading={saving} disabled={!url.trim()}>
            Gắn link
          </Button>
        </Flex>
      )}
    </Flex>
  );
}
