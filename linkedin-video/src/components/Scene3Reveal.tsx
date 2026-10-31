import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { JobPilotLogo } from "./JobPilotLogo";
import { DottedFlightPath } from "./DottedFlightPath";

export const Scene3Reveal: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Light sweep progress across first 25 frames
  const sweepProgress = interpolate(frame, [0, 28], [-20, 120], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Paper plane landing transition into logo
  const planeFlight = interpolate(frame, [0, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const logoSpring = spring({
    frame: frame - 18,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 120 },
  });

  const subSpring = spring({
    frame: frame - 28,
    fps,
    config: { damping: 12, mass: 0.6, stiffness: 130 },
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
        overflow: "hidden",
      }}
    >
      {/* Light Sweep Wipe */}
      <div
        style={{
          position: "absolute",
          top: "-50%",
          left: `${sweepProgress}%`,
          width: "400px",
          height: "200%",
          background: "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.9) 50%, rgba(255,255,255,0) 100%)",
          transform: "rotate(25deg)",
          filter: "blur(20px)",
          pointerEvents: "none",
          zIndex: 8,
        }}
      />

      {/* Flight Path where plane flies and lands in center */}
      {frame < 30 && (
        <DottedFlightPath
          startX={-100}
          startY={650}
          endX={540}
          endY={480}
          progress={planeFlight}
        />
      )}

      {/* Hero Glass Enclosure (Fills >60% of frame) */}
      <div
        style={{
          transform: `scale(${logoSpring}) translateY(${interpolate(logoSpring, [0, 1], [35, 0])}px)`,
          opacity: logoSpring,
          width: "880px",
          height: "760px",
          backgroundColor: "rgba(255, 255, 255, 0.92)",
          border: "2px solid rgba(255, 255, 255, 0.98)",
          borderRadius: "44px",
          boxShadow: "0 35px 80px -15px rgba(37, 99, 235, 0.18)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          padding: "64px",
          position: "relative",
          zIndex: 5,
        }}
      >
        {/* Soft Bloom Ring behind Logo */}
        <div
          style={{
            position: "absolute",
            width: "300px",
            height: "300px",
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(37, 99, 235, 0.22) 0%, rgba(37, 99, 235, 0) 70%)",
            top: "140px",
            pointerEvents: "none",
          }}
        />

        {/* Job Pilot Logo */}
        <JobPilotLogo size={140} showWordmark={false} />

        {/* Wordmark: Job Pilot */}
        <h1
          style={{
            fontSize: "140px",
            lineHeight: "1.02",
            fontWeight: 900,
            letterSpacing: "-0.05em",
            color: "#0B0F1A",
            margin: "32px 0 20px 0",
          }}
        >
          Job Pilot
        </h1>

        {/* Subtitle */}
        <div
          style={{
            transform: `translateY(${interpolate(subSpring, [0, 1], [25, 0])}px)`,
            opacity: subSpring,
            fontSize: "52px",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: "#475569",
            maxWidth: "760px",
            lineHeight: "1.2",
          }}
        >
          Autopilot for your <span style={{ color: "#2563EB" }}>job search.</span>
        </div>
      </div>
    </div>
  );
};
