import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME, containerStyle } from "../styles";

export const Scene4Evaluator: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  const cardSpring = spring({
    frame: frame - 10,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 110 },
  });

  // Stamp spring for AUTO-APPROVED
  const stampSpring = spring({
    frame: frame - 55,
    fps,
    config: { damping: 10, mass: 0.6, stiffness: 160 },
  });

  const matchPercent = Math.floor(
    interpolate(frame, [15, 60], [20, 94], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  return (
    <div style={containerStyle}>
      {/* Pill */}
      <div
        style={{
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
          backgroundColor: THEME.purpleLight,
          border: `1.5px solid ${THEME.purpleBorder}`,
          color: THEME.purple,
          borderRadius: "999px",
          padding: "8px 24px",
          fontSize: "18px",
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "16px",
        }}
      >
        <span>🎯</span>
        Smart Evaluator Engine
      </div>

      <h1
        style={{
          fontSize: "48px",
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
        AI-Powered Candidate Scoring
      </h1>

      <p
        style={{
          fontSize: "22px",
          color: THEME.textSecondary,
          textAlign: "center",
          maxWidth: "760px",
          margin: "0 0 32px 0",
          fontWeight: 500,
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
        }}
      >
        Evaluates tech fit, strict worldwide remote legality, and junior experience constraints in seconds.
      </p>

      {/* Main Evaluator Inspector Card */}
      <div
        style={{
          transform: `scale(${cardSpring})`,
          opacity: cardSpring,
          width: "100%",
          maxWidth: "840px",
          backgroundColor: THEME.cardBg,
          borderRadius: "22px",
          padding: "32px",
          border: `1.5px solid ${THEME.cardBorder}`,
          boxShadow: THEME.cardShadow,
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Job Header inside card */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "24px" }}>
          <div>
            <div style={{ fontSize: "14px", fontWeight: 700, color: THEME.blue, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Sample Evaluated Listing #2048
            </div>
            <div style={{ fontSize: "26px", fontWeight: 800, color: THEME.textPrimary, marginTop: "4px" }}>
              Junior AI & Full Stack Engineer (Remote)
            </div>
            <div style={{ fontSize: "16px", color: THEME.textMuted, marginTop: "2px" }}>
              Series A AI Startup • San Francisco, CA (100% Worldwide Remote)
            </div>
          </div>

          <div
            style={{
              textAlign: "right",
              backgroundColor: THEME.blueLight,
              padding: "12px 20px",
              borderRadius: "14px",
              border: `1px solid ${THEME.blueBorder}`,
            }}
          >
            <div style={{ fontSize: "13px", fontWeight: 700, color: THEME.blue }}>MATCH SCORE</div>
            <div
              style={{
                fontSize: "36px",
                fontWeight: 900,
                color: THEME.blue,
                fontFamily: "'JetBrains Mono', monospace",
                lineHeight: "1.1",
              }}
            >
              {matchPercent}%
            </div>
          </div>
        </div>

        {/* 4 Inspection Points */}
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {/* Criterion 1: Tech Stack */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 18px",
              backgroundColor: THEME.bg,
              borderRadius: "12px",
              border: `1px solid ${THEME.cardBorder}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "20px" }}>⚡</span>
              <div>
                <span style={{ fontWeight: 700, color: THEME.textPrimary, fontSize: "16px" }}>Tech Stack Fit: </span>
                <span style={{ color: THEME.textMuted, fontSize: "15px" }}>Python, FastAPI, React, LangChain, RAG</span>
              </div>
            </div>
            <span style={{ fontWeight: 700, color: THEME.emerald, fontSize: "16px" }}>+40 / 40 pts</span>
          </div>

          {/* Criterion 2: Geo / Visa Check */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 18px",
              backgroundColor: THEME.bg,
              borderRadius: "12px",
              border: `1px solid ${THEME.cardBorder}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "20px" }}>🌍</span>
              <div>
                <span style={{ fontWeight: 700, color: THEME.textPrimary, fontSize: "16px" }}>Location Legality: </span>
                <span style={{ color: THEME.textMuted, fontSize: "15px" }}>Worldwide Remote Verified (No US-only gate)</span>
              </div>
            </div>
            <span style={{ fontWeight: 700, color: THEME.emerald, fontSize: "16px" }}>PASSED</span>
          </div>

          {/* Criterion 3: Junior Band */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 18px",
              backgroundColor: THEME.bg,
              borderRadius: "12px",
              border: `1px solid ${THEME.cardBorder}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "20px" }}>🎓</span>
              <div>
                <span style={{ fontWeight: 700, color: THEME.textPrimary, fontSize: "16px" }}>Experience Level: </span>
                <span style={{ color: THEME.textMuted, fontSize: "15px" }}>0 - 2 Years (Junior Friendly)</span>
              </div>
            </div>
            <span style={{ fontWeight: 700, color: THEME.emerald, fontSize: "16px" }}>+20 / 20 pts</span>
          </div>

          {/* Criterion 4: USD Compensation */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 18px",
              backgroundColor: THEME.bg,
              borderRadius: "12px",
              border: `1px solid ${THEME.cardBorder}`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "20px" }}>💵</span>
              <div>
                <span style={{ fontWeight: 700, color: THEME.textPrimary, fontSize: "16px" }}>USD Salary Mention: </span>
                <span style={{ color: THEME.textMuted, fontSize: "15px" }}>$75,000 - $110,000 USD / year</span>
              </div>
            </div>
            <span style={{ fontWeight: 700, color: THEME.emerald, fontSize: "16px" }}>+10 / 10 pts</span>
          </div>
        </div>

        {/* Big AUTO-APPROVED Stamp Overlay */}
        {frame > 55 && (
          <div
            style={{
              position: "absolute",
              top: "40%",
              right: "40px",
              transform: `scale(${stampSpring}) rotate(-8deg)`,
              opacity: stampSpring,
              backgroundColor: THEME.emerald,
              color: "#FFFFFF",
              padding: "16px 36px",
              borderRadius: "16px",
              fontSize: "28px",
              fontWeight: 900,
              letterSpacing: "0.08em",
              boxShadow: "0 20px 40px rgba(5, 150, 105, 0.4)",
              border: "3px solid #FFFFFF",
              display: "flex",
              alignItems: "center",
              gap: "12px",
            }}
          >
            <span>✓</span> AUTO-APPROVED
          </div>
        )}
      </div>
    </div>
  );
};
