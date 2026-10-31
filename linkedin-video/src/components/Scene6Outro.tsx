import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME, containerStyle } from "../styles";

export const Scene6Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  const cardSpring = spring({
    frame: frame - 15,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 110 },
  });

  const ctaSpring = spring({
    frame: frame - 30,
    fps,
    config: { damping: 12, mass: 0.6, stiffness: 130 },
  });

  return (
    <div style={containerStyle}>
      {/* Header Pill */}
      <div
        style={{
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
          backgroundColor: THEME.orangeLight,
          border: `1.5px solid ${THEME.orangeBorder}`,
          color: THEME.orange,
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
        <span>🚀</span> Stop Shotgun Applying
      </div>

      <h1
        style={{
          fontSize: "52px",
          lineHeight: "1.15",
          fontWeight: 900,
          textAlign: "center",
          maxWidth: "880px",
          margin: "0 0 14px 0",
          letterSpacing: "-0.03em",
          color: THEME.textPrimary,
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
        }}
      >
        Automate the Search. <br />
        <span style={{ color: THEME.blue }}>Snipe the High-Signal Roles.</span>
      </h1>

      <p
        style={{
          fontSize: "24px",
          color: THEME.textSecondary,
          textAlign: "center",
          maxWidth: "760px",
          margin: "0 0 36px 0",
          fontWeight: 500,
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
        }}
      >
        Built with Python 3.12, FastAPI, MongoDB & Modern React Architecture.
      </p>

      {/* LinkedIn Discussion Prompt Card */}
      <div
        style={{
          transform: `scale(${cardSpring})`,
          opacity: cardSpring,
          width: "100%",
          maxWidth: "820px",
          backgroundColor: THEME.cardBg,
          borderRadius: "22px",
          padding: "32px 36px",
          border: `2px solid ${THEME.blueBorder}`,
          boxShadow: THEME.cardShadow,
          display: "flex",
          flexDirection: "column",
          gap: "16px",
          textAlign: "center",
          position: "relative",
        }}
      >
        <div style={{ fontSize: "18px", fontWeight: 800, color: THEME.blue, letterSpacing: "0.05em", textTransform: "uppercase" }}>
          Join The Conversation on LinkedIn 👇
        </div>

        <div style={{ fontSize: "28px", fontWeight: 800, color: THEME.textPrimary, lineHeight: "1.3" }}>
          "How many hours do you spend searching & filtering jobs each week?"
        </div>

        <div style={{ fontSize: "18px", color: THEME.textSecondary }}>
          Drop your answer and your preferred tech stack in the comments! Let's connect and share insights.
        </div>
      </div>

      {/* Author / Engineer Pill */}
      <div
        style={{
          transform: `translateY(${interpolate(ctaSpring, [0, 1], [30, 0])}px) scale(${ctaSpring})`,
          opacity: ctaSpring,
          display: "flex",
          alignItems: "center",
          gap: "16px",
          marginTop: "32px",
          backgroundColor: THEME.cardBg,
          padding: "12px 28px",
          borderRadius: "999px",
          border: `1.5px solid ${THEME.cardBorder}`,
          boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
        }}
      >
        <div
          style={{
            width: "44px",
            height: "44px",
            borderRadius: "50%",
            backgroundColor: THEME.blueLight,
            border: `2px solid ${THEME.blueBorder}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "20px",
            fontWeight: 800,
            color: THEME.blue,
          }}
        >
          IH
        </div>
        <div style={{ textAlign: "left" }}>
          <div style={{ fontSize: "18px", fontWeight: 800, color: THEME.textPrimary }}>
            Ibrahim Hamid
          </div>
          <div style={{ fontSize: "14px", color: THEME.textMuted }}>
            Full Stack & AI Engineer • Open Source Creator
          </div>
        </div>
      </div>
    </div>
  );
};
