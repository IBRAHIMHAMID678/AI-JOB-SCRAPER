import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME, containerStyle } from "../styles";

export const Scene2Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const heroSpring = spring({
    frame,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 120 },
  });

  const bento1 = spring({
    frame: frame - 15,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  const bento2 = spring({
    frame: frame - 28,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  const bento3 = spring({
    frame: frame - 40,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  const bento4 = spring({
    frame: frame - 52,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  return (
    <div style={containerStyle}>
      {/* Badge */}
      <div
        style={{
          transform: `scale(${heroSpring})`,
          opacity: heroSpring,
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
          marginBottom: "20px",
        }}
      >
        <span style={{ fontSize: "20px" }}>⚡</span>
        Autonomous Agentic System
      </div>

      {/* Main Title */}
      <h1
        style={{
          fontSize: "56px",
          lineHeight: "1.1",
          fontWeight: 900,
          textAlign: "center",
          maxWidth: "880px",
          margin: "0 0 16px 0",
          letterSpacing: "-0.03em",
          color: THEME.textPrimary,
          transform: `scale(${heroSpring})`,
          opacity: heroSpring,
        }}
      >
        Meet <span style={{ color: THEME.blue }}>AI Job Hunter</span> Pro
      </h1>

      <p
        style={{
          fontSize: "24px",
          color: THEME.textSecondary,
          textAlign: "center",
          maxWidth: "780px",
          margin: "0 0 40px 0",
          fontWeight: 500,
          lineHeight: "1.4",
          transform: `scale(${heroSpring})`,
          opacity: heroSpring,
        }}
      >
        The end-to-end mission control engine that scrapes 10+ global job boards in parallel, scores every posting with AI, and routes high-probability matches straight to you.
      </p>

      {/* 4-Bento Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "20px",
          width: "100%",
          maxWidth: "840px",
        }}
      >
        {/* Bento 1: Multi-Platform */}
        <div
          style={{
            transform: `translateY(${interpolate(bento1, [0, 1], [30, 0])}px) scale(${bento1})`,
            opacity: bento1,
            backgroundColor: THEME.cardBg,
            borderRadius: "20px",
            padding: "26px",
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: THEME.cardShadow,
          }}
        >
          <div style={{ fontSize: "32px", marginBottom: "12px" }}>🌐</div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: THEME.textPrimary, marginBottom: "8px" }}>
            10+ Parallel Platforms
          </div>
          <div style={{ fontSize: "16px", color: THEME.textMuted, lineHeight: "1.4" }}>
            Himalayas, Remotive, Jobicy, RemoteOK, JobSpy (LinkedIn/Indeed), WeWorkRemotely, NoDesk & The Muse.
          </div>
        </div>

        {/* Bento 2: 24h Freshness */}
        <div
          style={{
            transform: `translateY(${interpolate(bento2, [0, 1], [30, 0])}px) scale(${bento2})`,
            opacity: bento2,
            backgroundColor: THEME.cardBg,
            borderRadius: "20px",
            padding: "26px",
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: THEME.cardShadow,
          }}
        >
          <div style={{ fontSize: "32px", marginBottom: "12px" }}>⏱️</div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: THEME.textPrimary, marginBottom: "8px" }}>
            Strict 24h Freshness Gate
          </div>
          <div style={{ fontSize: "16px", color: THEME.textMuted, lineHeight: "1.4" }}>
            Automatically ignores stale, expired, and closed postings. You apply within the critical first 24 hours.
          </div>
        </div>

        {/* Bento 3: AI Scoring */}
        <div
          style={{
            transform: `translateY(${interpolate(bento3, [0, 1], [30, 0])}px) scale(${bento3})`,
            opacity: bento3,
            backgroundColor: THEME.cardBg,
            borderRadius: "20px",
            padding: "26px",
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: THEME.cardShadow,
          }}
        >
          <div style={{ fontSize: "32px", marginBottom: "12px" }}>🧠</div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: THEME.textPrimary, marginBottom: "8px" }}>
            Multi-Criteria AI Scoring
          </div>
          <div style={{ fontSize: "16px", color: THEME.textMuted, lineHeight: "1.4" }}>
            Scores tech stack match, verified remote work permission, junior experience bounds, and USD salary signal.
          </div>
        </div>

        {/* Bento 4: Auto Pipeline */}
        <div
          style={{
            transform: `translateY(${interpolate(bento4, [0, 1], [30, 0])}px) scale(${bento4})`,
            opacity: bento4,
            backgroundColor: THEME.cardBg,
            borderRadius: "20px",
            padding: "26px",
            border: `1.5px solid ${THEME.cardBorder}`,
            boxShadow: THEME.cardShadow,
          }}
        >
          <div style={{ fontSize: "32px", marginBottom: "12px" }}>📊</div>
          <div style={{ fontSize: "22px", fontWeight: 800, color: THEME.textPrimary, marginBottom: "8px" }}>
            Mission Control UI
          </div>
          <div style={{ fontSize: "16px", color: THEME.textMuted, lineHeight: "1.4" }}>
            Live SSE terminal stream, manual verification queue, and one-click export to Word (DOCX) or CSV.
          </div>
        </div>
      </div>
    </div>
  );
};
