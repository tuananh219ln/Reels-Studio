"use client";

import { GoogleOutlined } from "@ant-design/icons";
import { App, Button, Tooltip } from "antd";
import { useState } from "react";
import { ApiError, api, type SceneData, type VideoDetail } from "@/lib/api";
import { findGooglePhotos, useGoogleExtension } from "@/lib/googleExtension";
import { useEditor } from "./AutoSaveField";

// Results tried per scene before giving up on it: a site may refuse the download or be a stock site.
const TRIES_PER_SCENE = 5;

function keywordsOf(scene: SceneData): string {
  // Google Ảnh finds Vietnamese dishes best in Vietnamese; the first line of the text when there are no keywords.
  const words = scene.keywords.length ? scene.keywords.slice(0, 2).join(" ") : "";
  return words || scene.text.split("\n")[0].replaceAll("*", "").trim();
}

/**
 * "Lấy ảnh Google cho cảnh thiếu ảnh": with the team's Chrome extension, Google Ảnh is searched in the member's own
 * browser for every scene without a photo or clip, and the first photo the api accepts is put on it, marked "Tự
 * chọn, kiểm tra lại" (docs/decisions.md, 2026-11-08). Shown only when the extension answered.
 */
export default function GooglePhotosButton({ video, disabled }: { video: VideoDetail; disabled: boolean }) {
  const { message, modal } = App.useApp();
  const editor = useEditor();
  const present = useGoogleExtension();
  const [working, setWorking] = useState(false);
  if (!present) {
    return null;
  }
  const missing = [video.title_scene, ...video.scenes].filter(
    (scene): scene is SceneData => scene !== null && !scene.has_image && !scene.video,
  );

  async function run() {
    setWorking(true);
    try {
      await editor.flush();
      const wanted = missing.filter((scene) => keywordsOf(scene));
      const found = await findGooglePhotos(wanted.map(keywordsOf));
      let filled = 0;
      for (const [index, result] of found.results.entries()) {
        const scene = wanted[index];
        for (const photo of result.photos.slice(0, TRIES_PER_SCENE)) {
          try {
            editor.onSaved(
              await api<VideoDetail>(`/scenes/${scene.id}/media-from-url`, "POST", { url: photo.url, auto: true }),
            );
            filled += 1;
            break;
          } catch (err) {
            // A stock site, a site that refuses the download, not a photo: the next result.
            if (!(err instanceof ApiError) || err.status >= 500) {
              throw err;
            }
          }
        }
      }
      const total = wanted.length;
      if (found.captcha) {
        modal.warning({
          title: "Google hỏi CAPTCHA",
          content: `Đã lấy ảnh cho ${filled}/${total} cảnh. Hãy giải CAPTCHA trong tab Google vừa mở rồi bấm lại để lấy tiếp.`,
        });
      } else if (filled < total) {
        void message.warning(`Đã lấy ảnh Google cho ${filled}/${total} cảnh; cảnh còn lại hãy tìm hoặc dán ảnh khác.`);
      } else {
        void message.success(`Đã lấy ảnh Google cho ${filled} cảnh. Hãy xem lại ảnh của từng cảnh.`);
      }
    } catch (err) {
      void message.error(err instanceof Error ? err.message : "Không lấy được ảnh Google");
    } finally {
      setWorking(false);
    }
  }

  if (missing.length === 0) {
    return null;
  }
  return (
    <Tooltip title="Tiện ích Chrome mở Google Ảnh theo từ khóa của từng cảnh thiếu ảnh và gắn ảnh đầu tiên dùng được (bỏ ảnh của trang ảnh stock). Ảnh Google thường có bản quyền: hãy xem lại trước khi đăng.">
      <Button icon={<GoogleOutlined />} loading={working} disabled={disabled} onClick={() => void run()}>
        {working ? "Đang lấy ảnh Google…" : "Lấy ảnh Google cho cảnh thiếu ảnh"}
      </Button>
    </Tooltip>
  );
}
