import React from "react";
import { staticFile, useCurrentFrame, useVideoConfig } from "remotion";

export const BackgroundMesh: React.FC<{ brightness?: number }> = ({ brightness = 1.0 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Seamless loop angle: 0 to 2*PI across the 720 frames
  const angle = (frame / durationInFrames) * Math.PI * 2;

  // Orbiting subtle pastel gradient centers
  const blueX = 30 + 15 * Math.sin(angle);
  const blueY = 25 + 12 * Math.cos(angle);

  const lilacX = 75 + 12 * Math.cos(angle + 1.2);
  const lilacY = 65 + 15 * Math.sin(angle + 1.2);

  const peachX = 45 + 18 * Math.sin(angle + 2.8);
  const peachY = 80 + 12 * Math.cos(angle + 2.8);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundColor: "#F8F7F4",
        overflow: "hidden",
        zIndex: 0,
        filter: brightness !== 1.0 ? `brightness(${brightness})` : undefined,
      }}
    >
      {/* Drifting Soft Pastel Mesh Gradients (Native Gradient, zero CPU Gaussian blur) */}
      <div
        style={{
          position: "absolute",
          width: "900px",
          height: "900px",
          borderRadius: "50%",
          left: `${blueX}%`,
          top: `${blueY}%`,
          transform: "translate(-50%, -50%)",
          background: "radial-gradient(circle, rgba(219, 234, 254, 0.7) 0%, rgba(219, 234, 254, 0.35) 45%, rgba(248, 247, 244, 0) 70%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: "950px",
          height: "950px",
          borderRadius: "50%",
          left: `${lilacX}%`,
          top: `${lilacY}%`,
          transform: "translate(-50%, -50%)",
          background: "radial-gradient(circle, rgba(237, 233, 254, 0.65) 0%, rgba(237, 233, 254, 0.3) 45%, rgba(248, 247, 244, 0) 70%)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: "850px",
          height: "850px",
          borderRadius: "50%",
          left: `${peachX}%`,
          top: `${peachY}%`,
          transform: "translate(-50%, -50%)",
          background: "radial-gradient(circle, rgba(255, 237, 213, 0.6) 0%, rgba(255, 237, 213, 0.25) 45%, rgba(248, 247, 244, 0) 70%)",
          pointerEvents: "none",
        }}
      />

      {/* Lightweight Pre-rendered Paper Grain Texture */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `url(${staticFile("paper_grain.png")})`,
          backgroundRepeat: "repeat",
          opacity: 0.12,
          mixBlendMode: "multiply",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};
