"use client";

import { Collapse, Flex, Typography } from "antd";
import type { SceneData } from "@/lib/api";
import {
  SceneIssues,
  SceneKeywordsField,
  ScenePicture,
  ScenePromptField,
  SceneTextField,
  SceneVoiceField,
} from "../SceneCard";

/**
 * The studio's "Chỉnh cảnh N" panel beside the phone: everything about the scene being shown, so a scene is made
 * without leaving the studio. Its content (text, narration), its timing and text place (`timing`, the studio's own),
 * its photo or clip and how to find another. The fields are the scene card's own, saving the same way.
 */
export default function SceneInspector({
  scene,
  label,
  voiceEnabled,
  generating,
  timing,
  effects,
  layers,
}: {
  scene: SceneData;
  label: string;
  voiceEnabled: boolean;
  /** An image job is making this scene's photo. */
  generating: boolean;
  timing: React.ReactNode;
  /** "Hiệu ứng": the scene's transition, colour and clip speed (SceneEffects). */
  effects: React.ReactNode;
  /** "Chữ & sticker": the scene's layers (LayerList). */
  layers: React.ReactNode;
}) {
  return (
    <Flex vertical gap={8} data-testid="preview-scene-editor">
      <Typography.Text strong style={{ fontSize: 15 }}>
        Chỉnh {label.toLowerCase()}
      </Typography.Text>
      <SceneIssues scene={scene} />
      <Collapse
        size="small"
        ghost
        defaultActiveKey={["content", "layers", "timing", "effects", "media"]}
        items={[
          {
            key: "content",
            label: "Nội dung",
            children: (
              <Flex vertical gap={4}>
                <SceneTextField scene={scene} />
                <SceneVoiceField scene={scene} voiceEnabled={voiceEnabled} />
              </Flex>
            ),
          },
          ...(scene.is_title
            ? []
            : [{ key: "layers", label: `Chữ & sticker (${scene.layers.length})`, children: layers }]),
          { key: "timing", label: "Thời lượng và vị trí chữ", children: timing },
          { key: "effects", label: "Hiệu ứng", children: effects },
          {
            key: "media",
            label: scene.video ? "Video của cảnh" : "Ảnh của cảnh",
            children: <ScenePicture scene={scene} voiceEnabled={voiceEnabled} generating={generating} compact />,
          },
          {
            key: "search",
            label: "Tìm ảnh: từ khoá và prompt AI",
            children: (
              <Flex vertical gap={4}>
                <SceneKeywordsField scene={scene} />
                <ScenePromptField scene={scene} />
              </Flex>
            ),
          },
        ]}
      />
    </Flex>
  );
}
