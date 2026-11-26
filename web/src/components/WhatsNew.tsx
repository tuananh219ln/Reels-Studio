"use client";

import { BellOutlined } from "@ant-design/icons";
import { Badge, Button, Flex, Modal, Tooltip } from "antd";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { COLORS } from "@/app/theme";
import { api, type Me } from "@/lib/api";
import { type Changelog, readChangelog, unseenEntries } from "@/lib/changelog";
import { usePolling } from "@/lib/polling";
import ChangeList from "./ChangeList";
import { useMe } from "./MeContext";

// An open tab asks every few minutes whether a newer version went live (and at once when the tab comes back).
const VERSION_CHECK_MS = 5 * 60_000;

function newestKey(changelog: Changelog): string {
  const newest = changelog.entries[0];
  return newest ? `${newest.number}@${newest.merged_at}` : "";
}

/**
 * "Có gì mới" (docs/decisions/2026-11-26-whats-new.md): a bell with a dot while there are changes the member has not
 * seen, a window listing the changes that opens by itself once after a deploy brings new ones, and a bar asking an
 * open tab to reload once a newer version went live. `vertical` stacks the bell above the account on the rail.
 */
export default function WhatsNew({ children, vertical = false }: { children: React.ReactNode; vertical?: boolean }) {
  const { me, setMe } = useMe();
  const [changelog, setChangelog] = useState<Changelog | null>(null);
  const [open, setOpen] = useState(false);
  const [newVersion, setNewVersion] = useState(false);
  // The newest change this tab first read: a newer one later means a deploy with something for members went live
  // after the page loaded (a deploy of docs or tests alone asks no one to reload).
  const loadedNewest = useRef<string | null>(null);
  const opened = useRef(false);

  const check = useCallback(async () => {
    const latest = await readChangelog().catch(() => null);
    if (!latest) return;
    const newest = newestKey(latest);
    if (loadedNewest.current === null) {
      loadedNewest.current = newest;
      setChangelog(latest);
    } else if (newest !== loadedNewest.current) {
      setNewVersion(true);
    }
  }, []);
  useEffect(() => {
    void check();
  }, [check]);
  usePolling(check, VERSION_CHECK_MS);

  const entries = useMemo(() => changelog?.entries ?? [], [changelog]);
  // The mark is read once the list is here; `now` for a member without one is when the list arrived.
  const unseen = useMemo(() => unseenEntries(entries, me.changelog_seen_at), [entries, me.changelog_seen_at]);
  const unseenNumbers = useMemo(() => new Set(unseen.map((entry) => entry.number)), [unseen]);

  // Once per page load, and only with something new: the window opens by itself (not on "Có gì mới", which lists them).
  const onPage = usePathname() === "/whats-new";
  useEffect(() => {
    if (unseen.length > 0 && !opened.current && !onPage) {
      opened.current = true;
      setOpen(true);
    }
  }, [unseen.length, onPage]);

  function close() {
    setOpen(false);
    if (unseen.length === 0) return;
    const newest = unseen[0].merged_at;
    // Gone at once on this tab; the api keeps it for the member's other devices.
    setMe({ ...me, changelog_seen_at: newest });
    api<Me>("/me/changelog-seen", "PUT", { seen_at: newest }).then(setMe, () => undefined);
  }

  const bell =
    entries.length > 0 ? (
      <Tooltip title="Có gì mới" placement={vertical ? "right" : "top"}>
        <Button
          type="text"
          aria-label="Có gì mới"
          data-testid="whats-new-bell"
          onClick={() => setOpen(true)}
          icon={
            <Badge dot={unseen.length > 0} offset={[-2, 2]}>
              <BellOutlined style={{ fontSize: 18 }} />
            </Badge>
          }
          style={{ height: 40, width: 40, flex: "none" }}
        />
      </Tooltip>
    ) : null;

  return (
    <>
      <Flex vertical={vertical} align="center" gap={4} style={{ width: "100%" }}>
        <div style={{ flex: 1, minWidth: 0, width: vertical ? "100%" : undefined }}>{children}</div>
        {bell}
      </Flex>
      <Modal
        open={open}
        title="Có gì mới"
        onCancel={close}
        footer={
          <Flex justify="flex-end" gap={8}>
            <Link href="/whats-new" onClick={close}>
              <Button>Xem tất cả</Button>
            </Link>
            <Button type="primary" onClick={close}>
              Đã xem
            </Button>
          </Flex>
        }
        styles={{ body: { maxHeight: "60vh", overflowY: "auto", paddingRight: 4 } }}
      >
        <ChangeList entries={entries} unseen={unseenNumbers} onOpenGuide={close} />
      </Modal>
      {newVersion && (
        <Flex
          role="status"
          data-testid="new-version-bar"
          align="center"
          justify="center"
          gap={12}
          wrap
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            zIndex: 1100,
            padding: "8px 16px",
            background: COLORS.info,
            color: COLORS.surface,
          }}
        >
          <span>Đã có bản mới của Reels Studio. Tải lại trang để dùng bản mới.</span>
          <Button size="small" onClick={() => window.location.reload()}>
            Tải lại
          </Button>
        </Flex>
      )}
    </>
  );
}
