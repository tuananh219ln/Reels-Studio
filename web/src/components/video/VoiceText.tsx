"use client";

import { Flex, Typography } from "antd";
import type { SceneData, VideoDetail } from "@/lib/api";
import AutoSaveField from "./AutoSaveField";

function seconds(value: number): string {
  return value.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

/** A scene's voice text, and once a render has made it, the narration with its length. */
export default function VoiceText({ scene, save }: { scene: SceneData; save: (text: string) => Promise<VideoDetail> }) {
  // The script's lengths (docs/content.md): 8–12 words for the title's opening line, 8–15 for a scene.
  const words = { min: 8, max: scene.is_title ? 12 : 15 };
  const lengthened = scene.fitted_seconds > scene.seconds;
  const hint =
    [
      !scene.voice_text.trim() && scene.spoken_text && `Sẽ đọc chữ trên màn hình: ${scene.spoken_text}`,
      scene.spoken_text && !scene.voice_url && "Giọng đọc được tạo khi render",
    ]
      .filter(Boolean)
      .join(", ") || undefined;
  return (
    <Flex vertical gap={4}>
      <AutoSaveField
        label="Lời đọc"
        value={scene.voice_text}
        multiline
        placeholder="để trống thì đọc chữ trên màn hình; không có chữ thì cảnh im lặng"
        save={save}
        hint={hint}
        words={words}
      />
      {scene.voice_url && scene.voice_seconds !== null && (
        // One line: the player, then how long the narration is against the scene ("Lời đọc 3,7s → cảnh 4,3s").
        <Flex wrap gap="4px 10px" align="center" style={{ marginBottom: 8 }}>
          <audio
            key={scene.voice_url}
            src={scene.voice_url}
            controls
            preload="none"
            data-testid="voice-player"
            style={{ flex: "1 1 200px", maxWidth: 300, height: 32 }}
          />
          <Typography.Text
            type={lengthened ? "warning" : "secondary"}
            style={{ fontSize: 12, whiteSpace: "nowrap" }}
            data-testid="voice-length"
          >
            Lời đọc {seconds(scene.voice_seconds)}s → cảnh {seconds(lengthened ? scene.fitted_seconds : scene.seconds)}s
          </Typography.Text>
        </Flex>
      )}
    </Flex>
  );
}
