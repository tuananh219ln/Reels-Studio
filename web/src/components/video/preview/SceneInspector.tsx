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
import PhotoLayerPanel from "../PhotoLayerPanel";
import { photoLayer } from "../videoModes";

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
  editing = false,
  timing,
  effects,
  layers,
  sounds,
  saved = scene,
  backdrop = false,
}: {
  scene: SceneData;
  /** The scene as saved: over a backdrop the preview shows `scene` with the title scene's picture. */
  saved?: SceneData;
  /** "Video xuyên suốt": a content scene's own picture is only its "Ảnh món". */
  backdrop?: boolean;
  label: string;
  voiceEnabled: boolean;
  /** An image job is making this scene's photo. */
  generating: boolean;
  /** An image_edit job ("Sửa ảnh") is changing this scene's photo. */
  editing?: boolean;
  timing: React.ReactNode;
  /** "Hiệu ứng": the scene's transition, colour and clip speed (SceneEffects). */
  effects: React.ReactNode;
  /** "Chữ & sticker": the scene's layers (LayerList). */
  layers: React.ReactNode;
  /** "Âm thanh": the music's level here and the scene's sound effects (SoundList). */
  sounds: React.ReactNode;
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
        defaultActiveKey={["content", "layers", "sounds", "timing", "effects", "media"]}
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
          { key: "sounds", label: `Âm thanh (${scene.sounds.length})`, children: sounds },
          { key: "timing", label: "Thời lượng và vị trí chữ", children: timing },
          { key: "effects", label: "Hiệu ứng", children: effects },
          backdrop && !saved.is_title
            ? {
                key: "media",
                label: "Ảnh món",
                children: (
                  <Flex vertical gap={8}>
                    <PhotoLayerPanel scene={saved} />
                    {photoLayer(saved.layers) && (
                      <ScenePicture
                        scene={saved}
                        voiceEnabled={voiceEnabled}
                        generating={generating}
                        editing={editing}
                        compact
                      />
                    )}
                  </Flex>
                ),
              }
            : {
                key: "media",
                label: backdrop ? "Nền chung của video" : scene.video ? "Video của cảnh" : "Ảnh của cảnh",
                children: (
                  <ScenePicture
                    scene={saved}
                    voiceEnabled={voiceEnabled}
                    generating={generating}
                    editing={editing}
                    compact
                  />
                ),
              },
          {
            key: "search",
            label: "Tìm ảnh: từ khoá và prompt AI",
            children: (
              <Flex vertical gap={4}>
                <SceneKeywordsField scene={saved} />
                <ScenePromptField scene={saved} />
              </Flex>
            ),
          },
        ]}
      />
    </Flex>
  );
}
