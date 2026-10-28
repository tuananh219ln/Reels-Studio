import { CalculateMetadataFunction, Composition } from "remotion";
import { Reel } from "./Reel";
import { ReelProps, totalSeconds } from "./schema";
import sample from "../../samples/xuong-khop.json";

export const FPS = 30;

// Độ dài video tự tính theo tổng số giây của các cảnh
const calculateMetadata: CalculateMetadataFunction<ReelProps> = ({ props }) => ({
  durationInFrames: Math.round(totalSeconds(props) * FPS),
});

export const Root: React.FC = () => (
  <Composition
    id="Reel"
    component={Reel}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={FPS * 25}
    defaultProps={sample as ReelProps}
    calculateMetadata={calculateMetadata}
  />
);
