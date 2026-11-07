"use client";

import { Flex, Segmented, Select, Typography } from "antd";
import type { SceneData } from "@/lib/api";
import { CLIP_SPEEDS, COLOR_PRESETS, SCENE_TRANSITIONS, transitionLabel } from "./effects";

const VIDEO = "video";
const speedLabel = (speed: number) => `${speed.toLocaleString("vi-VN")}×`;

/**
 * "Hiệu ứng" in "Chỉnh cảnh N": the transition into this scene (or the video's), its colour preset drawn on its own
 * picture, and a clip's speed. Each choice saves at once and can be undone; the title scene has none of them.
 */
export default function SceneEffects({
  scene,
  videoTransition,
  editable,
  onPatch,
  backdrop = false,
}: {
  scene: SceneData;
  /** "Video xuyên suốt": the scenes join by hard cuts over one backdrop, so they have no effects of their own. */
  backdrop?: boolean;
  /** The video's own transition ("Thiết lập"), which a scene without its own takes. */
  videoTransition: string;
  editable: boolean;
  onPatch: (label: string, body: Record<string, unknown>) => void;
}) {
  if (scene.is_title) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Cảnh tiêu đề mở đầu video và là ảnh bìa, nên không có chuyển cảnh hay màu riêng.
      </Typography.Text>
    );
  }
  if (backdrop) {
    return (
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Video xuyên suốt nối các cảnh bằng cắt thẳng trên một nền chung, nên cảnh không có chuyển cảnh, màu hay tốc độ
        riêng. Tốc độ và đoạn của clip nền chỉnh ở cảnh tiêu đề.
      </Typography.Text>
    );
  }
  const picture = scene.frame_url ?? scene.preview_url;
  const colors = [{ value: null, label: "Gốc", css: undefined }, ...COLOR_PRESETS];
  return (
    <Flex vertical gap={12} data-testid="scene-effects">
      <Flex vertical gap={4}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          Chuyển cảnh vào cảnh này
        </Typography.Text>
        <Select
          aria-label="Chuyển cảnh vào cảnh này"
          value={scene.transition ?? VIDEO}
          disabled={!editable}
          onChange={(value: string) => onPatch("đổi chuyển cảnh", { transition: value === VIDEO ? null : value })}
          options={[
            { value: VIDEO, label: `Theo cả video (${transitionLabel(videoTransition)})` },
            ...SCENE_TRANSITIONS,
          ]}
        />
      </Flex>
      <Flex vertical gap={4}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          Màu
        </Typography.Text>
        <div className="preview-colors" role="group" aria-label="Màu của cảnh">
          {colors.map((item) => (
            <button
              key={item.value ?? "none"}
              type="button"
              className="preview-color"
              aria-pressed={(scene.color ?? null) === item.value}
              disabled={!editable}
              onClick={() => onPatch("đổi màu", { color: item.value })}
            >
              {picture ? (
                // eslint-disable-next-line @next/next/no-img-element -- the api draws the frame; next/image adds nothing
                <img src={picture} alt="" style={{ filter: item.css }} />
              ) : (
                <span />
              )}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Màu trên điện thoại là gần đúng; MP4 render ra mới là màu thật.
        </Typography.Text>
      </Flex>
      {scene.video && (
        <Flex vertical gap={4}>
          <Typography.Text strong style={{ fontSize: 13 }}>
            Tốc độ clip
          </Typography.Text>
          <Segmented
            size="small"
            aria-label="Tốc độ clip"
            value={scene.video.speed}
            disabled={!editable}
            onChange={(value) => onPatch("đổi tốc độ clip", { video_speed: value })}
            options={CLIP_SPEEDS.map((speed) => ({ value: speed, label: speedLabel(speed) }))}
          />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Cảnh giữ nguyên số giây; nhanh hơn thì lấy nhiều clip hơn, clip hết sớm thì đứng ở khung cuối.
          </Typography.Text>
        </Flex>
      )}
    </Flex>
  );
}
