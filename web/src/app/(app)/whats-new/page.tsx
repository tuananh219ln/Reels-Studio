"use client";

import { Card, Flex, Spin } from "antd";
import { useEffect, useRef, useState } from "react";
import ChangeList from "@/components/ChangeList";
import EmptyState from "@/components/EmptyState";
import GuideButton from "@/components/GuideButton";
import { useMe } from "@/components/MeContext";
import PageHeader from "@/components/PageHeader";
import { api, type Me } from "@/lib/api";
import { type Changelog, readChangelog, unseenEntries } from "@/lib/changelog";

/** "Có gì mới" as a page (docs/decisions/2026-11-26-whats-new.md): every change kept, newest first. What was new when
 * the page opened keeps its "Mới" while it is open, and counts as seen. */
export default function WhatsNewPage() {
  const { me, setMe } = useMe();
  const [changelog, setChangelog] = useState<Changelog | null | undefined>(undefined);
  const [unseen, setUnseen] = useState<Set<number>>(new Set());
  const marked = useRef(false);

  useEffect(() => {
    readChangelog()
      .catch(() => null)
      .then(setChangelog);
  }, []);

  useEffect(() => {
    if (!changelog || marked.current) return;
    marked.current = true;
    const fresh = unseenEntries(changelog.entries, me.changelog_seen_at);
    setUnseen(new Set(fresh.map((entry) => entry.number)));
    if (fresh.length > 0) {
      api<Me>("/me/changelog-seen", "PUT", { seen_at: fresh[0].merged_at }).then(setMe, () => undefined);
    }
  }, [changelog, me.changelog_seen_at, setMe]);

  return (
    <>
      <PageHeader
        title="Có gì mới"
        description="Các tính năng mới và lỗi đã sửa sau mỗi lần cập nhật app, mới nhất ở trên. Danh sách tự lấy từ các thay đổi đã đưa lên, không ai phải viết."
        actions={<GuideButton screen="whats-new" />}
      />
      {changelog === undefined ? (
        <Flex justify="center" style={{ padding: 32 }}>
          <Spin />
        </Flex>
      ) : !changelog || changelog.entries.length === 0 ? (
        <EmptyState description="Chưa có thay đổi nào. Danh sách có sau lần cập nhật app đầu tiên." />
      ) : (
        <Card>
          <ChangeList entries={changelog.entries} unseen={unseen} />
        </Card>
      )}
    </>
  );
}
