"use client";

import { EditOutlined, UndoOutlined } from "@ant-design/icons";
import { Alert, App, Button, Col, Flex, Popconfirm, Row, Segmented, Spin, Tag } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import DefaultMusicCard from "@/components/settings/DefaultMusicCard";
import { SettingsHeader } from "@/components/settings/SettingsBlocks";
import { AudioSettings, MotionSettings, TextSettings } from "@/components/video/VideoSettings";
import { api, errorMessage, type MyVideoDefaults, type VideoDefaults } from "@/lib/api";

type Scope = "mine" | "team";

const URLS: Record<Scope, string> = { mine: "/settings/my-video-defaults", team: "/settings/video-defaults" };
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

/** What new videos start with: the signed-in member's own defaults ("Của tôi", the team's until they save their own)
 * or the team's ("Của nhóm", for members without their own). Existing videos keep their own settings. Read-only until
 * "Chỉnh sửa"; the changes are kept on the page and sent together by "Lưu", or dropped by "Huỷ". */
export default function VideoDefaultsPage() {
  const { message } = App.useApp();
  const [scope, setScope] = useState<Scope>("mine");
  const [saved, setSaved] = useState<MyVideoDefaults | VideoDefaults | null>(null);
  const [draft, setDraft] = useState<VideoDefaults | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    async (which: Scope) => {
      try {
        setSaved(await api<MyVideoDefaults | VideoDefaults>(URLS[which]));
      } catch (err) {
        message.error(errorMessage(err));
      }
    },
    [message],
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loads on mount and on a new scope; state is set only after the request answers
    void load(scope);
  }, [load, scope]);

  const pending = useMemo(() => (saved && draft ? changes(saved, draft) : {}), [saved, draft]);
  const dirty = Object.keys(pending).length > 0;
  const editing = draft !== null;
  const mine = scope === "mine" && saved !== null && "own" in saved ? saved : null;

  async function save() {
    if (!dirty) {
      setDraft(null);
      return;
    }
    setBusy(true);
    try {
      setSaved(await api<MyVideoDefaults | VideoDefaults>(URLS[scope], "PUT", { values: pending }));
      setDraft(null);
      message.success(scope === "mine" ? "Đã lưu mặc định của bạn" : "Đã lưu mặc định của nhóm");
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function backToTeam() {
    setBusy(true);
    try {
      setSaved(await api<MyVideoDefaults>(URLS.mine, "DELETE"));
      message.success("Video mới của bạn sẽ dùng mặc định của nhóm");
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
        description={
          scope === "mine"
            ? "Video bạn tạo mới bắt đầu với các thiết lập này (cả nhạc nền mặc định); video nhân bản lấy theo video gốc. Video đã có giữ thiết lập riêng, đổi ở tab “Thiết lập” của từng video."
            : "Mặc định của nhóm: dùng cho thành viên chưa đặt mặc định riêng, và là điểm bắt đầu khi một thành viên đặt mặc định của mình."
        }
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
              {mine?.own && (
                <Popconfirm
                  title="Dùng lại mặc định của nhóm?"
                  description="Mặc định riêng của bạn sẽ bị bỏ; video đã có không đổi."
                  okText="Dùng mặc định nhóm"
                  cancelText="Huỷ"
                  onConfirm={() => void backToTeam()}
                >
                  <Button icon={<UndoOutlined />} disabled={busy}>
                    Dùng mặc định nhóm
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
      <Flex vertical gap={12} style={{ marginBottom: 16 }}>
        <Segmented<Scope>
          aria-label="Mặc định của"
          value={scope}
          disabled={editing}
          onChange={(next) => {
            setSaved(null);
            setScope(next);
          }}
          options={[
            { value: "mine", label: mine?.owner ? `Của tôi (${mine.owner})` : "Của tôi" },
            { value: "team", label: "Của nhóm" },
          ]}
        />
        {mine && (
          <Alert
            data-testid="defaults-whose"
            type={mine.own ? "success" : "info"}
            showIcon
            title={
              mine.own
                ? `Đang sửa mặc định riêng của tài khoản ${mine.owner}.`
                : `Tài khoản ${mine.owner} chưa có mặc định riêng nên đang dùng mặc định của nhóm. Lưu thay đổi ở đây sẽ tạo mặc định riêng cho bạn.`
            }
          />
        )}
        {scope === "team" && (
          <Alert
            data-testid="defaults-whose"
            type="warning"
            showIcon
            title="Đang sửa mặc định của cả nhóm: áp dụng cho các thành viên chưa có mặc định riêng."
          />
        )}
      </Flex>
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
