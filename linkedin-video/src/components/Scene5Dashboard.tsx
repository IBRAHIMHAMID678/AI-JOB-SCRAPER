import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME, containerStyle } from "../styles";

export const Scene5Dashboard: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  const macSpring = spring({
    frame: frame - 12,
    fps,
    config: { damping: 13, mass: 0.8, stiffness: 110 },
  });

  const badge1 = spring({ frame: frame - 30, fps, config: { damping: 12 } });
  const badge2 = spring({ frame: frame - 42, fps, config: { damping: 12 } });
  const badge3 = spring({ frame: frame - 54, fps, config: { damping: 12 } });

  return (
    <div style={containerStyle}>
      {/* Header Pill */}
      <div
        style={{
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
          backgroundColor: THEME.blueLight,
          border: `1.5px solid ${THEME.blueBorder}`,
          color: THEME.blue,
          borderRadius: "999px",
          padding: "8px 24px",
          fontSize: "18px",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "14px",
        }}
      >
        <span>🖥️</span>
        Mission Control Interface
      </div>

      <h1
        style={{
          fontSize: "46px",
          lineHeight: "1.15",
          fontWeight: 900,
          textAlign: "center",
          maxWidth: "880px",
          margin: "0 0 10px 0",
          letterSpacing: "-0.03em",
          color: THEME.textPrimary,
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
        }}
      >
        Live Real-Time Control Center
      </h1>

      <p
        style={{
          fontSize: "20px",
          color: THEME.textSecondary,
          textAlign: "center",
          maxWidth: "760px",
          margin: "0 0 24px 0",
          fontWeight: 500,
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
        }}
      >
        Filter, inspect full job requirements, view live logs, and export reports in 1 click.
      </p>

      {/* Mac App Mockup Window */}
      <div
        style={{
          transform: `scale(${macSpring})`,
          opacity: macSpring,
          width: "100%",
          maxWidth: "880px",
          backgroundColor: THEME.cardBg,
          borderRadius: "18px",
          border: `1.5px solid ${THEME.cardBorder}`,
          boxShadow: "0 30px 60px -15px rgba(15, 23, 42, 0.18)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          position: "relative",
        }}
      >
        {/* macOS Window Titlebar */}
        <div
          style={{
            height: "42px",
            backgroundColor: "#F1F5F9",
            borderBottom: "1px solid #E2E8F0",
            display: "flex",
            alignItems: "center",
            padding: "0 18px",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "#EF4444" }} />
            <span style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "#F59E0B" }} />
            <span style={{ width: "12px", height: "12px", borderRadius: "50%", backgroundColor: "#10B981" }} />
          </div>

          <div style={{ fontSize: "13px", fontWeight: 600, color: THEME.textMuted }}>
            AI Job Hunter Mission Control — http://localhost:8000
          </div>

          <div style={{ width: "50px" }} />
        </div>

        {/* Real Screenshot Preview */}
        <div style={{ width: "100%", height: "380px", overflow: "hidden", position: "relative" }}>
          <Img
            src={staticFile("hero.png")}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: "top center",
            }}
          />
        </div>
      </div>

      {/* 3 Floating Action Badges below */}
      <div
        style={{
          display: "flex",
          gap: "16px",
          marginTop: "20px",
          width: "100%",
          maxWidth: "880px",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            transform: `translateY(${interpolate(badge1, [0, 1], [20, 0])}px) scale(${badge1})`,
            opacity: badge1,
            backgroundColor: THEME.cardBg,
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: "0 8px 20px rgba(0,0,0,0.06)",
            borderRadius: "12px",
            padding: "10px 18px",
            fontSize: "15px",
            fontWeight: 700,
            color: THEME.textPrimary,
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span>📄</span> One-Click Word (DOCX) & CSV Export
        </div>

        <div
          style={{
            transform: `translateY(${interpolate(badge2, [0, 1], [20, 0])}px) scale(${badge2})`,
            opacity: badge2,
            backgroundColor: THEME.cardBg,
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: "0 8px 20px rgba(0,0,0,0.06)",
            borderRadius: "12px",
            padding: "10px 18px",
            fontSize: "15px",
            fontWeight: 700,
            color: THEME.textPrimary,
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span>📡</span> Real-Time Server-Sent Log Stream
        </div>

        <div
          style={{
            transform: `translateY(${interpolate(badge3, [0, 1], [20, 0])}px) scale(${badge3})`,
            opacity: badge3,
            backgroundColor: THEME.cardBg,
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: "0 8px 20px rgba(0,0,0,0.06)",
            borderRadius: "12px",
            padding: "10px 18px",
            fontSize: "15px",
            fontWeight: 700,
            color: THEME.textPrimary,
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span>⚡</span> Mark-as-Applied Tracker
        </div>
      </div>
    </div>
  );
};
