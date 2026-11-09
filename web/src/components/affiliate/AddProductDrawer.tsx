"use client";

import { InboxOutlined } from "@ant-design/icons";
import { Alert, App, Button, Flex, Form, Input, Segmented, Select, Tag, Typography, Upload } from "antd";
import Link from "next/link";
import { useState } from "react";
import { api, errorMessage, type AffiliateImport, type AffiliateImportPreview, type AffiliateOptions } from "@/lib/api";
import FormDrawer from "@/components/FormDrawer";

export type AddMode = "links" | "file";

/** Where the products go: a Page (into the group it posts) or a group chosen by name. */
type Target = "page" | "topic";

const MAX_FILE_BYTES = 2_000_000;

/** "Thêm sản phẩm": paste Shopee links or drop Shopee Affiliate's file, and the rest is filled in by itself. Typing
 * every field stays possible ("Nhập tay"), for TikTok Shop and for a team without a Shopee App ID. */
export default function AddProductDrawer({
  mode,
  options,
  startTopicId,
  onClose,
  onManual,
  onDone,
}: {
  /** null: closed. */
  mode: AddMode | null;
  options: AffiliateOptions;
  /** The group open on the list, chosen to start with. */
  startTopicId?: number;
  onClose: () => void;
  onManual: () => void;
  onDone: () => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const [tab, setTab] = useState<AddMode>("links");
  const [topicId, setTopicId] = useState<number>();
  const [target, setTarget] = useState<Target>("topic");
  const [pageId, setPageId] = useState<number>();
  const [preview, setPreview] = useState<AffiliateImportPreview | null>(null);
  const [links, setLinks] = useState("");
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [result, setResult] = useState<AffiliateImport | null>(null);
  const [busy, setBusy] = useState(false);
  const [openedAs, setOpenedAs] = useState<AddMode | null>(null);

  // Each opening starts clean on the tab it was opened for (state adjusted while rendering, not in an effect).
  if (mode !== openedAs) {
    setOpenedAs(mode);
    if (mode !== null) {
      setTab(mode);
      setLinks("");
      setFile(null);
      setResult(null);
      setPreview(null);
      // From a group on the list, that group; else my first Page that posts a group, else a group by name.
      const myPage = options.pages.find((page) => page.mine && page.knowledge_topic_id !== null);
      setTarget(startTopicId === undefined && myPage ? "page" : "topic");
      setPageId(myPage?.id);
      setTopicId(startTopicId);
    }
  }

  // A Page's products go into the group it posts; with one topic group there is nothing to choose.
  const chosenPage = options.pages.find((page) => page.id === pageId);
  const topic =
    target === "page"
      ? (chosenPage?.knowledge_topic_id ?? undefined)
      : (topicId ?? (options.topics.length === 1 ? options.topics[0].id : undefined));
  const topicName = options.topics.find((one) => one.id === topic)?.name;

  /** What "Nhập" would do with the file in this group, row by row; nothing is written. */
  async function loadPreview(text: string, group: number | undefined) {
    setPreview(null);
    if (group === undefined || !text) {
      return;
    }
    try {
      setPreview(
        await api<AffiliateImportPreview>("/affiliate-products/import/preview", "POST", {
          knowledge_topic_id: group,
          text,
        }),
      );
    } catch (err) {
      message.error(errorMessage(err));
    }
  }
  const taking = preview ? preview.rows.filter((row) => row.state !== "others").length : 0;
  const pasted = links
    .split(/\s+/)
    .map((link) => link.trim())
    .filter(Boolean);
  const ready =
    topic !== undefined &&
    (tab === "links" ? pasted.length > 0 && options.shopee_lookup : file !== null && (preview === null || taking > 0));

  async function submit() {
    if (!ready) {
      return;
    }
    setBusy(true);
    try {
      if (tab === "links") {
        const done = await api<{ added: number; skipped: string[] }>("/affiliate-products/links", "POST", {
          knowledge_topic_id: topic,
          links: pasted,
        });
        const skipped = done.skipped.length > 0 ? `, ${done.skipped.length} link đã có trong danh sách` : "";
        message.success(`Đã thêm ${done.added} sản phẩm, đang lấy thông tin từ Shopee${skipped}`);
        await onDone();
        onClose();
        return;
      }
      const done = await api<AffiliateImport>("/affiliate-products/import", "POST", {
        knowledge_topic_id: topic,
        text: file?.text ?? "",
      });
      const counts = [`thêm ${done.added}`, done.updated > 0 ? `cập nhật ${done.updated}` : ""].filter(Boolean);
      message.success(`Đã nhập vào “${topicName}”: ${counts.join(", ")} sản phẩm`);
      setPreview(null);
      if (done.errors.length > 0 || done.kept > 0 || !done.lookup) {
        // Stay open so the member reads which rows were left out and what is still to fill in.
        setResult(done);
        setFile(null);
        await onDone();
        return;
      }
      await onDone();
      onClose();
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title="Thêm sản phẩm"
      open={mode !== null}
      onClose={onClose}
      onOk={submit}
      okText={tab === "links" ? "Thêm" : preview ? `Nhập ${taking} sản phẩm` : "Nhập"}
      confirmLoading={busy}
      okButtonProps={{ disabled: !ready }}
      width={560}
    >
      <Flex vertical gap={16}>
        <Segmented<AddMode>
          block
          aria-label="Cách thêm"
          value={tab}
          onChange={(next) => {
            setTab(next);
            setResult(null);
          }}
          options={[
            { value: "links", label: "Dán link Shopee" },
            { value: "file", label: "Nhập file" },
          ]}
        />
        <Form layout="vertical" requiredMark={false} component="div">
          <Form.Item label="Nhập vào" required>
            <Flex vertical gap={8}>
              <Segmented<Target>
                aria-label="Nhập vào"
                value={target}
                onChange={(next) => {
                  setTarget(next);
                  const group =
                    next === "page" ? (chosenPage?.knowledge_topic_id ?? undefined) : (topicId ?? undefined);
                  void loadPreview(file?.text ?? "", group);
                }}
                options={[
                  { value: "page", label: "Theo Page" },
                  { value: "topic", label: "Theo nhóm" },
                ]}
              />
              {target === "page" ? (
                <>
                  <Select
                    aria-label="Page"
                    placeholder="Chọn Page"
                    value={pageId}
                    onChange={(id) => {
                      setPageId(id);
                      const group = options.pages.find((page) => page.id === id)?.knowledge_topic_id ?? undefined;
                      void loadPreview(file?.text ?? "", group);
                    }}
                    options={[...options.pages]
                      .sort((a, b) => Number(b.mine) - Number(a.mine))
                      .map((page) => ({
                        value: page.id,
                        disabled: page.knowledge_topic_id === null,
                        label:
                          page.name +
                          (page.mine ? "" : ` · ${page.owner_name ?? "chưa có chủ"}`) +
                          (page.knowledge_topic_id === null ? " (chưa gắn nhóm chủ đề)" : ""),
                      }))}
                    notFoundContent="Chưa có Page nào"
                  />
                  {topicName && (
                    <Typography.Text type="secondary">
                      Sản phẩm vào nhóm “{topicName}”, dùng cho mọi Page đăng nhóm này.
                    </Typography.Text>
                  )}
                </>
              ) : (
                <Select
                  aria-label="Nhóm chủ đề"
                  placeholder="Chọn nhóm chủ đề"
                  value={topic}
                  onChange={(id) => {
                    setTopicId(id);
                    void loadPreview(file?.text ?? "", id);
                  }}
                  options={[...options.topics]
                    .sort((a, b) => Number(b.mine) - Number(a.mine))
                    .map((one) => ({ value: one.id, label: one.name }))}
                />
              )}
            </Flex>
          </Form.Item>
          {tab === "links" ? (
            <>
              {!options.shopee_lookup && (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  title="Cần một tài khoản Shopee có App ID để tự lấy thông tin từ link"
                  description={
                    <>
                      Thêm App ID và Secret ở{" "}
                      <Link href="/settings/affiliate-accounts">Cài đặt › Tài khoản affiliate</Link>. Chưa có thì dùng{" "}
                      <Typography.Link onClick={() => setTab("file")}>Nhập file</Typography.Link> từ Shopee Affiliate.
                    </>
                  }
                />
              )}
              <Form.Item
                label="Link sản phẩm"
                extra="Mỗi dòng một link, tối đa 50. Tên, shop, số sao, lượt bán, giá và hoa hồng được lấy từ Shopee sau vài giây; link bạn dán được giữ làm link affiliate."
              >
                <Input.TextArea
                  aria-label="Link sản phẩm"
                  value={links}
                  onChange={(event) => setLinks(event.target.value)}
                  placeholder={"https://s.shopee.vn/...\nhttps://shopee.vn/..."}
                  autoSize={{ minRows: 4, maxRows: 12 }}
                  disabled={!options.shopee_lookup}
                />
              </Form.Item>
            </>
          ) : (
            <Form.Item
              label="File từ Shopee Affiliate"
              extra="Trong Shopee Affiliate, mở Lấy link hàng loạt, tạo link rồi tải file CSV về và thả vào đây. Sản phẩm bạn đã thêm trước đó được cập nhật link và hoa hồng; sản phẩm của người khác giữ nguyên link của họ."
            >
              <Upload.Dragger
                accept=".csv,text/csv"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(picked) => {
                  if (picked.size > MAX_FILE_BYTES) {
                    message.error("File quá lớn, hãy chia nhỏ");
                    return Upload.LIST_IGNORE;
                  }
                  picked.text().then(
                    (text) => {
                      setFile({ name: picked.name, text });
                      setResult(null);
                      void loadPreview(text, topic);
                    },
                    () => message.error("Không đọc được file"),
                  );
                  return false;
                }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">{file ? file.name : "Bấm hoặc kéo file CSV vào đây"}</p>
              </Upload.Dragger>
            </Form.Item>
          )}
        </Form>
        {tab === "file" && preview && (
          <Alert
            type={preview.rows.some((row) => row.state === "others") || preview.errors.length > 0 ? "warning" : "info"}
            showIcon
            title="Xem trước"
            description={
              <Flex vertical gap={6} data-testid="import-preview">
                <Flex wrap gap={6}>
                  <Tag color="green">Mới {preview.rows.filter((row) => row.state === "new").length}</Tag>
                  <Tag>Đã có của bạn {preview.rows.filter((row) => row.state === "mine").length}</Tag>
                  <Tag color="gold">Của người khác {preview.rows.filter((row) => row.state === "others").length}</Tag>
                  <Tag color="red">Lỗi {preview.errors.length}</Tag>
                </Flex>
                {preview.rows.some((row) => row.state === "mine") && (
                  <span>Sản phẩm đã có của bạn được cập nhật giá, hoa hồng và link.</span>
                )}
                {preview.rows
                  .filter((row) => row.state === "others")
                  .map((row) => (
                    <span key={row.row}>
                      Dòng {row.row}: “{row.name}” của {row.by} (nhóm {row.topic}) được giữ nguyên link của họ.
                    </span>
                  ))}
                {preview.errors.map((error) => (
                  <span key={error.row}>
                    Dòng {error.row}: {error.message}
                  </span>
                ))}
              </Flex>
            }
          />
        )}
        {result && (
          <Alert
            type={result.errors.length > 0 ? "warning" : "info"}
            showIcon
            title={`Đã nhập ${result.added + result.updated} sản phẩm${
              result.errors.length > 0 ? `, bỏ qua ${result.errors.length} dòng` : ""
            }`}
            description={
              <Flex vertical gap={4}>
                {result.others.map((other) => (
                  <span key={`other-${other.row}`}>
                    Dòng {other.row}: “{other.name}” của {other.by} được giữ nguyên link của họ.
                  </span>
                ))}
                {result.errors.map((error) => (
                  <span key={error.row}>
                    Dòng {error.row}: {error.message}
                  </span>
                ))}
                {!result.lookup && (
                  <span>
                    File không có số sao, lượt bán và loại shop: điền ngay trên dòng của từng sản phẩm trong danh sách
                    rồi duyệt, hoặc thêm App ID Shopee để chúng được lấy tự động.
                  </span>
                )}
              </Flex>
            }
          />
        )}
        <Typography.Text type="secondary">
          Sản phẩm TikTok Shop hoặc muốn tự điền từng ô?{" "}
          <Button type="link" size="small" style={{ padding: 0 }} onClick={onManual}>
            Nhập tay
          </Button>
        </Typography.Text>
      </Flex>
    </FormDrawer>
  );
}
