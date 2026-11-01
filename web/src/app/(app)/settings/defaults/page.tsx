"use client";

import { App, Col, Row, Spin, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { AudioSettings, MotionSettings, TextSettings } from "@/components/video/VideoSettings";
import { api, errorMessage, type VideoDefaults } from "@/lib/api";

/** What every new video starts with. Existing videos keep their own settings. */
export default function VideoDefaultsPage() {
  const { message } = App.useApp();
  const [values, setValues] = useState<VideoDefaults | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setValues(await api<VideoDefaults>("/settings/video-defaults"));
    } catch (err) {
      message.error(errorMessage(err));
    }
  }, [message]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount; state is set only after the request answers
    void load();
  }, [load]);

  async function change(changes: Partial<VideoDefaults>) {
    setBusy(true);
    try {
      setValues(await api<VideoDefaults>("/settings/video-defaults", "PUT", { values: changes }));
      message.success("Đã lưu mặc định");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Typography.Paragraph type="secondary" style={{ margin: "0 0 16px", maxWidth: 760 }}>
        Video tạo mới bắt đầu với các thiết lập này; video nhân bản lấy theo video gốc. Video đã có giữ thiết lập riêng:
        đổi ở tab “Thiết lập” của từng video, hoặc bấm “Lấy theo mặc định nhóm” ở đó.
      </Typography.Paragraph>
      {values === null ? (
        <Spin />
      ) : (
        <Row gutter={[16, 16]} style={{ maxWidth: 1100 }}>
          <Col xs={24} lg={12}>
            <AudioSettings values={values} onChange={change} disabled={busy} showMusicVolume />
          </Col>
          <Col xs={24} lg={12}>
            <Row gutter={[16, 16]}>
              <Col span={24}>
                <MotionSettings values={values} onChange={change} disabled={busy} />
              </Col>
              <Col span={24}>
                <TextSettings values={values} onChange={change} disabled={busy} />
              </Col>
            </Row>
          </Col>
        </Row>
      )}
    </>
  );
}
