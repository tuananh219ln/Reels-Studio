"use client";

import { EditOutlined } from "@ant-design/icons";
import { App, Button, Col, Flex, Row, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
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
      <Flex wrap gap={12} justify="space-between" align="flex-start" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary" style={{ margin: 0, maxWidth: 680 }}>
          Video tạo mới bắt đầu với các thiết lập này; video nhân bản lấy theo video gốc. Video đã có giữ thiết lập
          riêng: đổi ở tab “Thiết lập” của từng video, hoặc bấm “Lấy theo mặc định nhóm” ở đó.
        </Typography.Paragraph>
        {saved !== null &&
          (editing ? (
            <Flex gap={8} align="center">
              {dirty && <Tag color="warning">Có thay đổi chưa lưu</Tag>}
              <Button disabled={busy} onClick={() => setDraft(null)}>
                Huỷ
              </Button>
              <Button type="primary" loading={busy} disabled={!dirty} onClick={() => void save()}>
                Lưu
              </Button>
            </Flex>
          ) : (
            <Button icon={<EditOutlined />} onClick={() => setDraft(saved)}>
              Chỉnh sửa
            </Button>
          ))}
      </Flex>
      {values === null ? (
        <Spin />
      ) : (
        // Two columns (sound, then picture with text under it); three side by side on a wide screen.
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12} xxl={8}>
            <AudioSettings values={values} onChange={change} disabled={!editing || busy} showMusicVolume />
          </Col>
          <Col xs={24} lg={12} xxl={16}>
            <Row gutter={[16, 16]}>
              <Col span={24} xxl={12}>
                <MotionSettings values={values} onChange={change} disabled={!editing || busy} />
              </Col>
              <Col span={24} xxl={12}>
                <TextSettings values={values} onChange={change} disabled={!editing || busy} />
              </Col>
            </Row>
          </Col>
        </Row>
      )}
    </>
  );
}
