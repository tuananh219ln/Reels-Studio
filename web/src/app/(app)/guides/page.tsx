"use client";

import EmptyState from "@/components/EmptyState";
import MarkdownReader from "@/components/MarkdownReader";
import PageHeader from "@/components/PageHeader";
import { COLORS } from "@/app/theme";
import { api, errorMessage, formatDateTime } from "@/lib/api";
import { type ChangeEntry, guideUpdates, isRecent, readChangelog } from "@/lib/changelog";
import { useUrlChoice } from "@/lib/urlState";
import { App, Card, Col, Flex, Menu, Row, Spin, Typography } from "antd";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";

type Listed = { slug: string; screen: string | null; title: string };
type Guide = Listed & { body: string };

// What each screen is called in the menu; a screen without a name here is listed under its own key.
const SCREENS: Record<string, string> = {
  affiliate: "Affiliate",
  videos: "Video",
  knowledge: "Kho kiến thức",
  "whats-new": "Có gì mới",
  telegram: "Thông báo Telegram",
};
const OTHER = "Khác";

function Guides() {
  const { message } = App.useApp();
  const [guides, setGuides] = useState<Listed[] | null>(null);
  const [slug, setSlug] = useUrlChoice<string | null>("guide", null);
  const [guide, setGuide] = useState<Guide | null>(null);
  // "Có gì mới": the change that last wrote each guide, so a guide a new feature brought is marked by itself.
  const [updates, setUpdates] = useState<Record<string, ChangeEntry>>({});

  useEffect(() => {
    readChangelog()
      .then((changelog) => changelog && setUpdates(guideUpdates(changelog.entries)))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    api<Listed[]>("/guides")
      .then(setGuides)
      .catch((err) => message.error(errorMessage(err)));
  }, [message]);

  const chosen = guides?.find((one) => one.slug === slug)?.slug ?? guides?.[0]?.slug ?? null;
  useEffect(() => {
    if (chosen === null) return;
    let current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- clears the old guide while the new one is read
    setGuide(null);
    api<Guide>(`/guides/${chosen}`)
      .then((body) => current && setGuide(body))
      .catch((err) => message.error(errorMessage(err)));
    return () => {
      current = false;
    };
  }, [chosen, message]);

  const screens = [...new Set((guides ?? []).map((one) => one.screen ?? OTHER))];
  return (
    <>
      <PageHeader
        title="Tất cả hướng dẫn"
        description="Hướng dẫn của mọi màn, gom theo màn. Mỗi màn cũng có nút “Hướng dẫn” ở đầu trang."
      />
      {guides === null ? (
        <Flex justify="center" style={{ padding: 32 }}>
          <Spin />
        </Flex>
      ) : guides.length === 0 ? (
        <EmptyState description="Chưa có hướng dẫn nào." />
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={8} xl={6}>
            <Card size="small" styles={{ body: { padding: 4 } }}>
              <Menu
                data-testid="guides-menu"
                mode="inline"
                style={{ border: "none" }}
                selectedKeys={chosen ? [chosen] : []}
                onClick={({ key }) => setSlug(key)}
                items={screens.map((screen) => ({
                  type: "group" as const,
                  key: `screen:${screen}`,
                  label: SCREENS[screen] ?? screen,
                  children: guides
                    .filter((one) => (one.screen ?? OTHER) === screen)
                    .map((one) => ({
                      key: one.slug,
                      label: (
                        <Flex align="center" gap={8}>
                          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>
                            {one.title.replace(/^Hướng dẫn:\s*/, "")}
                          </span>
                          {isRecent(updates[one.slug]) && (
                            <span style={{ color: COLORS.primary, fontSize: 12, flex: "none" }}>Mới</span>
                          )}
                        </Flex>
                      ),
                    })),
                }))}
              />
            </Card>
          </Col>
          <Col xs={24} md={16} xl={18}>
            <Card>
              {guide && updates[guide.slug] && (
                <Typography.Paragraph type="secondary" style={{ fontSize: 13 }} data-testid="guide-updated">
                  Cập nhật cùng <Link href="/whats-new">{updates[guide.slug].title}</Link>,{" "}
                  {formatDateTime(updates[guide.slug].merged_at)}
                </Typography.Paragraph>
              )}
              {guide ? (
                <MarkdownReader body={guide.body} />
              ) : (
                <Flex justify="center" style={{ padding: 32 }}>
                  <Spin />
                </Flex>
              )}
            </Card>
          </Col>
        </Row>
      )}
      <Typography.Text type="secondary" style={{ display: "block", marginTop: 12, fontSize: 12 }}>
        Hướng dẫn nằm trong app và đổi cùng tính năng, nên luôn khớp với bản đang chạy.
      </Typography.Text>
    </>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Guides />
    </Suspense>
  );
}
