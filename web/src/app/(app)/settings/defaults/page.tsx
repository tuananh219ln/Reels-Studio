"use client";

import { EditOutlined } from "@ant-design/icons";
import { App, Button, Col, Flex, Row, Spin, Tag } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { AudioSettings, MotionSettings, TextSettings } from "@/components/video/VideoSettings";
import { api, errorMessage, type VideoDefaults } from "@/lib/api";

/** The fields of `draft` that differ from `saved`: what "Lưu" sends. */
function changes(saved: VideoDefaults, draft: VideoDefaults): Partial<VideoDefaults> {
  return Object.fromEntries(
    Object.entries(draft).filter(
      ([key, value]) => JSON.stringify(value) !== JSON.stringify(saved[key as keyof VideoDefaults]),
    ),
  ) as Partial<VideoDefaults>;
}

/** What every new video starts with. Existing videos keep their own settings. Read-only until "Chỉnh sửa"; the
 * changes are kept on the page and sent together by "Lưu", or dropped by "Huỷ". */
export default function VideoDefaultsPage() {
  const { message } = App.useApp();
  const [saved, setSaved] = useState<VideoDefaults | null>(null);
  const [draft, setDraft] = useState<VideoDefaults | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSaved(await api<VideoDefaults>("/settings/video-defaults"));
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
      setSaved(await api<VideoDefaults>("/settings/video-defaults", "PUT", { values: pending }));
      setDraft(null);
      message.success("Đã lưu mặc định");
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
        description="Video tạo mới bắt đầu với các thiết lập này; video nhân bản lấy theo video gốc. Video đã có giữ thiết lập riêng: đổi ở tab “Thiết lập” của từng video, hoặc bấm “Lấy theo mặc định nhóm” ở đó."
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
            <Button icon={<EditOutlined />} onClick={() => setDraft(saved)}>
              Chỉnh sửa
            </Button>
          ))
        }
      />
      {values === null ? (
        <Spin />
      ) : (
        // Sound and picture down the left, the text (the longest) on the right on a wide screen; one column below that,
        // since the settings' segmented choices need about 400 px.
        <Row gutter={[16, 16]}>
          <Col xs={24} xxl={10}>
            <Flex vertical gap={16}>
              <AudioSettings values={values} onChange={change} disabled={!editing || busy} showMusicVolume />
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
