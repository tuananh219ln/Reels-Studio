"use client";

import { App, Form, Input, Select, Switch, Typography } from "antd";
import { useEffect, useId, useState } from "react";
import { api, errorMessage, upload, type MusicTrack } from "@/lib/api";
import { useMusicOptions } from "./useTracks";
import FormDrawer from "@/components/FormDrawer";

export const MAX_MUSIC_BYTES = 20 * 1024 * 1024;

type Fields = {
  name: string;
  topics: string[];
  mood: string;
  license_note: string;
  claimed_on_youtube?: boolean;
  claimed_note?: string;
};

/** What the modal works on: a chosen MP3 to add to the library, or a track to edit. */
export type TrackTarget = { file: File } | { track: MusicTrack };

function defaultName(file: File): string {
  return file.name.replace(/\.mp3$/i, "");
}

/** Adds a track (name, topics, mood, source) or edits one; `onDone` gets the saved track. */
export default function TrackModal({
  target,
  onClose,
  onDone,
}: {
  target: TrackTarget | null;
  onClose: () => void;
  onDone: (track: MusicTrack) => void | Promise<void>;
}) {
  const { message } = App.useApp();
  const { topics, moods } = useMusicOptions();
  const [form] = Form.useForm<Fields>();
  const formName = useId();
  const [busy, setBusy] = useState(false);
  const adding = target !== null && "file" in target;
  const claimed = Form.useWatch("claimed_on_youtube", form);

  useEffect(() => {
    if (target === null) {
      return;
    }
    form.setFieldsValue(
      "file" in target
        ? { name: defaultName(target.file), topics: [], mood: undefined, license_note: "" }
        : { ...target.track },
    );
  }, [form, target]);

  async function submit(fields: Fields) {
    if (target === null) {
      return;
    }
    setBusy(true);
    try {
      // A new track is never claimed yet: the flag is set by editing it once a claim is found.
      const { claimed_on_youtube, claimed_note, ...added } = fields;
      const track =
        "file" in target
          ? await upload<MusicTrack>("/music", target.file, added)
          : await api<MusicTrack>(`/music/${target.track.id}`, "PATCH", {
              ...added,
              claimed_on_youtube: claimed_on_youtube ?? false,
              claimed_note: claimed_note ?? "",
            });
      await onDone(track);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <FormDrawer
      title={adding ? "Thêm vào thư viện nhạc" : "Sửa bài nhạc"}
      open={target !== null}
      onClose={onClose}
      onOk={() => form.submit()}
      okText={adding ? "Thêm" : "Lưu"}
      cancelText="Huỷ"
      confirmLoading={busy}
      forceRender
    >
      {adding && <Typography.Paragraph type="secondary">File: {target.file.name}</Typography.Paragraph>}
      <Form name={formName} form={form} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item
          label="Tên bài"
          name="name"
          rules={[
            { required: true, whitespace: true, message: "Nhập tên bài" },
            { max: 200, message: "Tên bài tối đa 200 ký tự" },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          label="Chủ đề"
          name="topics"
          rules={[{ required: true, message: "Chọn ít nhất một chủ đề" }]}
          extra="Theo các nhóm chủ đề ở Kho kiến thức; “chung” hợp với mọi chủ đề."
        >
          <Select mode="multiple" aria-label="Chủ đề" options={topics.map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item label="Mood" name="mood" rules={[{ required: true, message: "Chọn mood" }]}>
          <Select aria-label="Mood" options={moods.map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item
          label="Nguồn / giấy phép"
          name="license_note"
          rules={[{ max: 500, message: "Tối đa 500 ký tự" }]}
          extra="Ví dụ: Pixabay Music (miễn phí dùng thương mại). Nhạc có bản quyền có thể khiến video bị tắt tiếng."
        >
          <Input />
        </Form.Item>
        {!adding && (
          <>
            <Form.Item
              label="Đã bị claim trên YouTube"
              name="claimed_on_youtube"
              valuePropName="checked"
              extra="Bật khi YouTube Studio báo bài này bị claim Content ID: không video nào chọn được bài này nữa (kể cả nhạc mặc định). Video đã có bài này giữ nguyên."
            >
              <Switch aria-label="Đã bị claim trên YouTube" />
            </Form.Item>
            {claimed && (
              <Form.Item
                label="Ghi chú claim"
                name="claimed_note"
                rules={[{ max: 500, message: "Tối đa 500 ký tự" }]}
                extra="Video nào, ai claim, ngày. Ví dụ: Video 409 – HAAWK Publishing – 26/11/2026."
              >
                <Input />
              </Form.Item>
            )}
          </>
        )}
      </Form>
    </FormDrawer>
  );
}
