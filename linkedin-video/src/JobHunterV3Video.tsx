import React from "react";
import { Audio, Series, interpolate, staticFile, useCurrentFrame } from "remotion";
import { BackgroundMesh } from "./components/BackgroundMesh";
import { Scene1Hook } from "./components/Scene1Hook";
import { Scene2Pain } from "./components/Scene2Pain";
import { Scene3Reveal } from "./components/Scene3Reveal";
import { Scene4System } from "./components/Scene4System";
import { Scene5Control } from "./components/Scene5Control";
import { Scene6Payoff } from "./components/Scene6Payoff";
import { Scene7CTA } from "./components/Scene7CTA";

export const JobHunterV3Video: React.FC = () => {
  const frame = useCurrentFrame();

  // Background brightness release swell during Scene 6 Payoff (frame 570 - 660)
  const bgBrightness = interpolate(frame, [570, 600, 660], [1.0, 1.05, 1.0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "relative",
        width: "1080px",
        height: "1350px",
        overflow: "hidden",
        backgroundColor: "#F8F7F4",
      }}
    >
      {/* Universal Synced Audio Track */}
      <Audio src={staticFile("audio_track.wav")} volume={1.0} />

      {/* Global Drifting Pastel Gradient Mesh Background */}
      <BackgroundMesh brightness={bgBrightness} />

      {/* Storyboard Scenes */}
      <div style={{ position: "relative", zIndex: 5, width: "100%", height: "100%" }}>
        <Series>
          {/* 0:00 - 0:03 (90 frames): HOOK */}
          <Series.Sequence durationInFrames={90}>
            <Scene1Hook />
          </Series.Sequence>

          {/* 0:03 - 0:06 (90 frames): THE PAIN */}
          <Series.Sequence durationInFrames={90}>
            <Scene2Pain />
          </Series.Sequence>

          {/* 0:06 - 0:08 (60 frames): THE REVEAL */}
          <Series.Sequence durationInFrames={60}>
            <Scene3Reveal />
          </Series.Sequence>

          {/* 0:08 - 0:14 (180 frames): THE SYSTEM */}
          <Series.Sequence durationInFrames={180}>
            <Scene4System />
          </Series.Sequence>

          {/* 0:14 - 0:19 (150 frames): THE CONTROL */}
          <Series.Sequence durationInFrames={150}>
            <Scene5Control />
          </Series.Sequence>

          {/* 0:19 - 0:22 (90 frames): THE PAYOFF */}
          <Series.Sequence durationInFrames={90}>
            <Scene6Payoff />
          </Series.Sequence>

          {/* 0:22 - 0:24 (60 frames): CTA */}
          <Series.Sequence durationInFrames={60}>
            <Scene7CTA />
          </Series.Sequence>
        </Series>
      </div>
    </div>
  );
};
