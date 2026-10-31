import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { DottedFlightPath } from "./DottedFlightPath";

export const Scene6Payoff: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const textSpring = spring({
    frame,
    fps,
    config: { damping: 12, mass: 0.6, stiffness: 140 },
  });

  const checkSpring = spring({
    frame: frame - 16,
    fps,
    config: { damping: 10, mass: 0.5, stiffness: 160 },
  });

  // SVG checkmark stroke drawing
  const checkProgress = interpolate(frame, [16, 45], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const strokeOffset = 180 * (1 - checkProgress);

  // Flight path swooping upward
  const flightProgress = interpolate(frame, [0, 85], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "80px",
        boxSizing: "border-box",
        fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif",
      }}
    >
      <DottedFlightPath
        startX={-100}
        startY={850}
        endX={1180}
        endY={280}
        progress={flightProgress}
      />

      {/* Big Animated Glowing Emerald Checkmark Badge */}
      <div
        style={{
          transform: `scale(${checkSpring})`,
          opacity: checkSpring,
          width: "180px",
          height: "180px",
          borderRadius: "50%",
          backgroundColor: "rgba(22, 163, 74, 0.14)",
          border: "4px solid rgba(22, 163, 74, 0.4)",
          boxShadow: "0 0 80px rgba(22, 163, 74, 0.35), inset 0 0 30px rgba(22, 163, 74, 0.2)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: "48px",
          position: "relative",
          zIndex: 10,
        }}
      >
        <svg width="100" height="100" viewBox="0 0 100 100" fill="none">
          <path
            d="M25 52 L43 70 L78 30"
            stroke="#16A34A"
            strokeWidth="12"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="180"
            strokeDashoffset={strokeOffset}
          />
        </svg>
      </div>

      {/* Big Kinetic Typography: "Find the right job. Skip the noise." */}
      <div
        style={{
          transform: `scale(${textSpring}) translateY(${interpolate(textSpring, [0, 1], [35, 0])}px)`,
          opacity: textSpring,
          textAlign: "center",
          zIndex: 10,
        }}
      >
        <div
          style={{
            fontSize: "125px",
            lineHeight: "1.02",
            fontWeight: 900,
            letterSpacing: "-0.05em",
            color: "#0B0F1A",
          }}
        >
          Find the <span style={{ color: "#2563EB" }}>right</span> job.
        </div>
        <div
          style={{
            fontSize: "125px",
            lineHeight: "1.02",
            fontWeight: 900,
            letterSpacing: "-0.05em",
            color: "#0B0F1A",
            marginTop: "16px",
          }}
        >
          Skip the <span style={{ color: "#16A34A" }}>noise.</span>
        </div>
      </div>
    </div>
  );
};
