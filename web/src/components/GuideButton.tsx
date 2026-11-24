"use client";

import MarkdownReader from "@/components/MarkdownReader";
import { api, errorMessage } from "@/lib/api";
import { QuestionCircleOutlined } from "@ant-design/icons";
import { App, Button, Drawer, Flex, Segmented, Spin } from "antd";
import { useState } from "react";

type Listed = { slug: string; screen: string | null; title: string };
type Guide = Listed & { body: string };

/** "Hướng dẫn" of a screen: the guides shipped with the api for it (docs/decisions/2026-11-25-in-app-guides.md), in a
 * drawer. Nothing is asked until it is opened; with several guides a switch picks one. */
export default function GuideButton({ screen }: { screen: string }) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [guides, setGuides] = useState<Listed[] | null>(null);
  const [slug, setSlug] = useState<string>();
  const [guide, setGuide] = useState<Guide | null>(null);

  async function read(next: string) {
    setSlug(next);
    setGuide(null);
    try {
      setGuide(await api<Guide>(`/guides/${next}`));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  async function show() {
    setOpen(true);
    if (guides !== null) return;
    try {
      const found = await api<Listed[]>(`/guides?screen=${screen}`);
      setGuides(found);
      if (found.length > 0) await read(found[0].slug);
    } catch (err) {
      message.error(errorMessage(err));
    }
  }

  return (
    <>
      <Button icon={<QuestionCircleOutlined />} onClick={() => void show()}>
        Hướng dẫn
      </Button>
      <Drawer title="Hướng dẫn" open={open} onClose={() => setOpen(false)} width={860} destroyOnHidden={false}>
        {guides === null || (guides.length > 0 && guide === null) ? (
          <Flex justify="center" style={{ padding: 32 }}>
            <Spin />
          </Flex>
        ) : guides.length === 0 ? (
          "Màn này chưa có hướng dẫn."
        ) : (
          <Flex vertical gap={16}>
            {guides.length > 1 && (
              <Segmented
                aria-label="Chọn hướng dẫn"
                value={slug}
                onChange={(value) => void read(String(value))}
                options={guides.map((one) => ({ value: one.slug, label: one.title.replace(/^Hướng dẫn:\s*/, "") }))}
              />
            )}
            {guide && <MarkdownReader body={guide.body} />}
          </Flex>
        )}
      </Drawer>
    </>
  );
}
