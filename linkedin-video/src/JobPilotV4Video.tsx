import React from "react";
import { Audio, Series, staticFile } from "remotion";
import { JobPilotMesh } from "./components/JobPilotMesh";
import { Scene1Hook } from "./components/Scene1Hook";
import { Scene2Pain } from "./components/Scene2Pain";
import { Scene3Reveal } from "./components/Scene3Reveal";
import { Scene4UniversalDemo } from "./components/Scene4UniversalDemo";
import { Scene5Control } from "./components/Scene5Control";
import { Scene6Payoff } from "./components/Scene6Payoff";
import { Scene7CTA } from "./components/Scene7CTA";

export const JobPilotV4Video: React.FC = () => {
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
      {/* 24-second Synchronized 115 BPM Audio */}
      <Audio src={staticFile("audio_track.wav")} volume={1.0} />

      {/* Dynamic Full-Bleed Pastel Field per scene */}
      <JobPilotMesh />

      {/* Strict 24-second Storyboard Sequence */}
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

          {/* 0:08 - 0:15 (210 frames): UNIVERSAL DEMO (4 diverse fields) */}
          <Series.Sequence durationInFrames={210}>
            <Scene4UniversalDemo />
          </Series.Sequence>

          {/* 0:15 - 0:19 (120 frames): THE CONTROL */}
          <Series.Sequence durationInFrames={120}>
            <Scene5Control />
          </Series.Sequence>

          {/* 0:19 - 0:21.67 (80 frames): THE PAYOFF */}
          <Series.Sequence durationInFrames={80}>
            <Scene6Payoff />
          </Series.Sequence>

          {/* 0:21.67 - 0:24 (70 frames): CTA */}
          <Series.Sequence durationInFrames={70}>
            <Scene7CTA />
          </Series.Sequence>
        </Series>
      </div>
    </div>
  );
};
