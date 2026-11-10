"use client";

import { EditOutlined, UndoOutlined } from "@ant-design/icons";
import { App, Button, Col, Flex, Popconfirm, Row, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import DefaultMusicCard from "@/components/settings/DefaultMusicCard";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { AudioSettings, MotionSettings, TextSettings } from "@/components/video/VideoSettings";
import { api, errorMessage, type MyVideoDefaults, type VideoDefaults } from "@/lib/api";

const DEFAULTS_URL = "/settings/my-video-defaults";
/** Shown on the page, never sent back. */
const READ_ONLY = new Set(["music_track", "own", "owner"]);

/** The fields of `draft` that differ from `saved`: what "Lưu" sends. */
function changes(saved: VideoDefaults, draft: VideoDefaults): Partial<VideoDefaults> {
  return Object.fromEntries(
    Object.entries(draft).filter(
      ([key, value]) =>
        !READ_ONLY.has(key) && JSON.stringify(value) !== JSON.stringify(saved[key as keyof VideoDefaults]),
    ),
  ) as Partial<VideoDefaults>;
}

/** What the signed-in member's new videos start with: their own defaults, the app's built-in ones until they save
 * their own. There is no team level: a teammate's defaults never reach them. Existing videos keep their own settings.
 * Read-only until "Chỉnh sửa"; the changes are kept on the page and sent together by "Lưu", or dropped by "Huỷ". */
export default function VideoDefaultsPage() {
  const { message } = App.useApp();
  const [saved, setSaved] = useState<MyVideoDefaults | null>(null);
  const [draft, setDraft] = useState<VideoDefaults | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSaved(await api<MyVideoDefaults>(DEFAULTS_URL));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  const pending = useMemo(() => (saved && draft ? changes(saved, draft) : {}), [saved, draft]);
  const dirty = Object.keys(pending).length > 0;
  const editing = draft !== null;

  async function save() {
    if (!dirty) {
      setDraft(null);
      return;
    }
    setBusy(true);
    try {
      setSaved(await api<MyVideoDefaults>(DEFAULTS_URL, "PUT", { values: pending }));
      setDraft(null);
      message.success("Đã lưu mặc định của bạn");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function backToBuiltIn() {
    setBusy(true);
    try {
      setSaved(await api<MyVideoDefaults>(DEFAULTS_URL, "DELETE"));
      message.success("Video mới của bạn sẽ dùng mặc định gốc của app");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const values = draft ?? saved;
  const change = (next: Partial<VideoDefaults>) => setDraft((current) => (current ? { ...current, ...next } : current));

  return (
    <>
      <SettingsHeader
        title="Thiết lập mặc định"
        description="Video bạn tạo mới bắt đầu với các thiết lập này (cả nhạc nền mặc định); video nhân bản lấy theo video gốc. Video đã có giữ thiết lập riêng, đổi ở tab “Thiết lập” của từng video."
        actions={
          saved !== null &&
          (editing ? (
            <>
              {dirty && <Tag color="warning">Có thay đổi chưa lưu</Tag>}
              <Button disabled={busy} onClick={() => setDraft(null)}>
                Huỷ
              </Button>
              <Button type="primary" loading={busy} disabled={!dirty} onClick={() => void save()}>
                Lưu
              </Button>
            </>
          ) : (
            <>
              {saved.own && (
                <Popconfirm
                  title="Về mặc định gốc của app?"
                  description="Mặc định riêng của bạn sẽ bị bỏ; video đã có không đổi."
                  okText="Về mặc định gốc"
                  cancelText="Huỷ"
                  onConfirm={() => void backToBuiltIn()}
                >
                  <Button icon={<UndoOutlined />} disabled={busy}>
                    Về mặc định gốc
                  </Button>
                </Popconfirm>
              )}
              <Button icon={<EditOutlined />} onClick={() => setDraft(saved)}>
                Chỉnh sửa
              </Button>
            </>
          ))
        }
      />
      {/* Read-only fields are greyed by antd; this line says why, so they do not read as broken. */}
      {!editing && values !== null && (
        <Typography.Paragraph type="secondary" style={{ marginTop: -4 }} data-testid="defaults-read-only">
          Đang xem. Bấm “Chỉnh sửa” để đổi, rồi “Lưu” một lần cho tất cả.
        </Typography.Paragraph>
      )}
      {values === null ? (
        <Spin />
      ) : (
        // Sound and picture down the left, the text (the longest) on the right on a wide screen; one column below that,
        // since the settings' segmented choices need about 400 px.
        <Row gutter={[16, 16]}>
          <Col xs={24} xxl={10}>
            <Flex vertical gap={16}>
              <AudioSettings values={values} onChange={change} disabled={!editing || busy} showMusicVolume />
              <DefaultMusicCard values={values} onChange={change} disabled={!editing || busy} />
              <MotionSettings values={values} onChange={change} disabled={!editing || busy} />
            </Flex>
          </Col>
          <Col xs={24} xxl={14}>
            <TextSettings values={values} onChange={change} disabled={!editing || busy} />
          </Col>
        </Row>
      )}
    </>
  );
}
