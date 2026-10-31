import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { JobPilotLogo } from "./JobPilotLogo";

export const Scene7CTA: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cardSpring = spring({
    frame,
    fps,
    config: { damping: 13, mass: 0.6, stiffness: 130 },
  });

  const buttonSpring = spring({
    frame: frame - 12,
    fps,
    config: { damping: 11, mass: 0.5, stiffness: 150 },
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
      {/* Hero Glass Card (Fills >60% of frame) */}
      <div
        style={{
          transform: `scale(${cardSpring}) translateY(${interpolate(cardSpring, [0, 1], [30, 0])}px)`,
          opacity: cardSpring,
          width: "880px",
          height: "760px",
          backgroundColor: "rgba(255, 255, 255, 0.94)",
          border: "2px solid rgba(255, 255, 255, 0.98)",
          borderRadius: "44px",
          boxShadow: "0 35px 80px -15px rgba(37, 99, 235, 0.16)",
          padding: "64px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "space-between",
          textAlign: "center",
        }}
      >
        {/* Job Pilot Logo + Headline */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <JobPilotLogo size={110} showWordmark={false} />
          <h1
            style={{
              fontSize: "105px",
              lineHeight: "1.05",
              fontWeight: 900,
              letterSpacing: "-0.04em",
              color: "#0B0F1A",
              margin: "24px 0 10px 0",
            }}
          >
            Job Pilot
          </h1>
          <div style={{ fontSize: "48px", fontWeight: 700, color: "#64748B", letterSpacing: "-0.02em" }}>
            Autopilot for your job search.
          </div>
        </div>

        {/* Bold Button-Style Pill */}
        <div
          style={{
            transform: `scale(${buttonSpring})`,
            opacity: buttonSpring,
            backgroundColor: "#2563EB",
            color: "#FFFFFF",
            padding: "24px 64px",
            borderRadius: "999px",
            fontSize: "44px",
            fontWeight: 900,
            letterSpacing: "-0.02em",
            boxShadow: "0 20px 40px rgba(37, 99, 235, 0.4)",
            display: "flex",
            alignItems: "center",
            gap: "16px",
          }}
        >
          <span>✈</span> Comment 'PILOT' for Access
        </div>

        {/* Small Discreet Line: Built by Ibrahim Hamid */}
        <div
          style={{
            fontSize: "26px",
            fontWeight: 700,
            color: "#94A3B8",
            letterSpacing: "0.04em",
            textTransform: "uppercase",
          }}
        >
          Built by Ibrahim Hamid
        </div>
      </div>
    </div>
  );
};
