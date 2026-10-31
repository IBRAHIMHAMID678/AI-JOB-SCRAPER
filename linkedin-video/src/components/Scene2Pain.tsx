import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { DottedFlightPath } from "./DottedFlightPath";

export const Scene2Pain: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Beat 1: 0 - 30 frames (0:03 - 0:04) -> "Ghost listings."
  const beat1Spring = spring({
    frame,
    fps,
    config: { damping: 12, mass: 0.5, stiffness: 150 },
  });
  const ghostDissolve = interpolate(frame, [18, 29], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Beat 2: 30 - 60 frames (0:04 - 0:05) -> "'Remote' but US-only."
  const beat2Spring = spring({
    frame: frame - 30,
    fps,
    config: { damping: 12, mass: 0.5, stiffness: 150 },
  });
  const strikeProgress = interpolate(frame, [40, 53], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Beat 3: 60 - 90 frames (0:05 - 0:06) -> "'Entry level' needing 6 years."
  const beat3Spring = spring({
    frame: frame - 60,
    fps,
    config: { damping: 12, mass: 0.5, stiffness: 150 },
  });
  const flipAngle = interpolate(frame, [68, 82], [0, 180], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Flight path animation
  const flightProgress = interpolate(frame, [0, 90], [0, 1], {
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
        alignItems: "center",
        justifyContent: "center",
        padding: "80px",
        boxSizing: "border-box",
        fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif",
      }}
    >
      <DottedFlightPath
        startX={1120}
        startY={250}
        endX={-50}
        endY={550}
        progress={flightProgress}
      />

      {/* Beat 1: "Ghost listings." (Fills >60% of frame with oversized hero card) */}
      {frame < 30 && (
        <div
          style={{
            transform: `scale(${beat1Spring}) translateY(${interpolate(beat1Spring, [0, 1], [40, 0])}px)`,
            opacity: beat1Spring,
            width: "880px",
            height: "720px",
            backgroundColor: "rgba(255, 255, 255, 0.92)",
            border: "2px solid rgba(255, 255, 255, 0.98)",
            borderRadius: "36px",
            boxShadow: "0 30px 70px -15px rgba(220, 38, 38, 0.15)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "36px",
            textAlign: "center",
            padding: "48px",
          }}
        >
          {/* Big Glossy Ghost Icon with particle dissolve */}
          <div
            style={{
              width: "170px",
              height: "170px",
              borderRadius: "44px",
              backgroundColor: "rgba(254, 226, 226, 0.7)",
              border: "3px solid rgba(254, 202, 202, 0.9)",
              boxShadow: "0 25px 50px -10px rgba(220, 38, 38, 0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "90px",
              opacity: ghostDissolve,
              transform: `scale(${ghostDissolve}) translateY(${(1 - ghostDissolve) * -40}px)`,
            }}
          >
            👻
          </div>

          <div
            style={{
              fontSize: "125px",
              lineHeight: "1.02",
              fontWeight: 900,
              letterSpacing: "-0.04em",
              color: "#0B0F1A",
            }}
          >
            <span style={{ color: "#DC2626" }}>Ghost</span> listings.
          </div>

          <div
            style={{
              fontSize: "48px",
              fontWeight: 700,
              color: "#64748B",
            }}
          >
            Never reviewed. Zero replies.
          </div>
        </div>
      )}

      {/* Beat 2: "'Remote' but US-only." */}
      {frame >= 30 && frame < 60 && (
        <div
          style={{
            transform: `scale(${beat2Spring}) translateY(${interpolate(beat2Spring, [0, 1], [40, 0])}px)`,
            opacity: beat2Spring,
            width: "880px",
            height: "720px",
            backgroundColor: "rgba(255, 255, 255, 0.92)",
            border: "2px solid rgba(255, 255, 255, 0.98)",
            borderRadius: "36px",
            boxShadow: "0 30px 70px -15px rgba(234, 88, 12, 0.15)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "36px",
            textAlign: "center",
            padding: "48px",
          }}
        >
          <div
            style={{
              width: "170px",
              height: "170px",
              borderRadius: "44px",
              backgroundColor: "rgba(255, 237, 213, 0.8)",
              border: "3px solid rgba(254, 215, 170, 0.9)",
              boxShadow: "0 25px 50px -10px rgba(234, 88, 12, 0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "90px",
            }}
          >
            🚫
          </div>

          <div
            style={{
              fontSize: "115px",
              lineHeight: "1.05",
              fontWeight: 900,
              letterSpacing: "-0.04em",
              color: "#0B0F1A",
              position: "relative",
            }}
          >
            <span style={{ position: "relative", display: "inline-block", padding: "0 10px" }}>
              "Remote"
              <svg
                style={{
                  position: "absolute",
                  left: 0,
                  top: "52%",
                  width: "100%",
                  height: "18px",
                  overflow: "visible",
                  pointerEvents: "none",
                }}
              >
                <line
                  x1="0"
                  y1="9"
                  x2={`${strikeProgress}%`}
                  y2="9"
                  stroke="#DC2626"
                  strokeWidth="14"
                  strokeLinecap="round"
                />
              </svg>
            </span>{" "}
            but <span style={{ color: "#DC2626" }}>US-only.</span>
          </div>

          <div
            style={{
              fontSize: "48px",
              fontWeight: 700,
              color: "#64748B",
            }}
          >
            Hidden in fine print.
          </div>
        </div>
      )}

      {/* Beat 3: "'Entry level' needing 6 years." */}
      {frame >= 60 && (
        <div
          style={{
            transform: `scale(${beat3Spring}) translateY(${interpolate(beat3Spring, [0, 1], [40, 0])}px)`,
            opacity: beat3Spring,
            width: "880px",
            height: "720px",
            backgroundColor: "rgba(255, 255, 255, 0.92)",
            border: "2px solid rgba(255, 255, 255, 0.98)",
            borderRadius: "36px",
            boxShadow: "0 30px 70px -15px rgba(124, 58, 237, 0.15)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "36px",
            textAlign: "center",
            padding: "48px",
          }}
        >
          {/* 3D Flipping Label */}
          <div style={{ perspective: "1000px" }}>
            <div
              style={{
                width: "480px",
                height: "140px",
                position: "relative",
                transformStyle: "preserve-3d",
                transform: `rotateY(${flipAngle}deg)`,
              }}
            >
              {/* Front side: "Entry Level" */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  backfaceVisibility: "hidden",
                  backgroundColor: "rgba(255, 255, 255, 0.95)",
                  border: "2px solid rgba(255, 255, 255, 0.98)",
                  borderRadius: "32px",
                  boxShadow: "0 25px 50px -10px rgba(11, 15, 26, 0.12)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "56px",
                  fontWeight: 900,
                  color: "#2563EB",
                  letterSpacing: "-0.03em",
                }}
              >
                "Entry Level"
              </div>

              {/* Back side: "Senior Only" */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  backfaceVisibility: "hidden",
                  transform: "rotateY(180deg)",
                  backgroundColor: "rgba(254, 226, 226, 0.85)",
                  border: "2px solid rgba(220, 38, 38, 0.4)",
                  borderRadius: "32px",
                  boxShadow: "0 25px 50px -10px rgba(220, 38, 38, 0.2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "56px",
                  fontWeight: 900,
                  color: "#DC2626",
                  letterSpacing: "-0.03em",
                }}
              >
                Senior Only ⚠️
              </div>
            </div>
          </div>

          <div
            style={{
              fontSize: "105px",
              lineHeight: "1.05",
              fontWeight: 900,
              letterSpacing: "-0.04em",
              color: "#0B0F1A",
            }}
          >
            needs <span style={{ color: "#DC2626" }}>6+</span> years.
          </div>

          <div
            style={{
              fontSize: "48px",
              fontWeight: 700,
              color: "#64748B",
            }}
          >
            Unrealistic expectations.
          </div>
        </div>
      )}
    </div>
  );
};
