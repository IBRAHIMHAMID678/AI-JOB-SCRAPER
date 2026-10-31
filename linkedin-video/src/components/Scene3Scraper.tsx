import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { THEME, containerStyle } from "../styles";

export const Scene3Scraper: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleSpring = spring({
    frame,
    fps,
    config: { damping: 14, mass: 0.8, stiffness: 100 },
  });

  // Animated live counter: 0 -> 1,284
  const liveCount = Math.floor(
    interpolate(frame, [10, 80], [120, 1284], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const sources = [
    { name: "LinkedIn & Indeed (JobSpy Engine)", count: 420, icon: "💼", speed: "42 req/s", status: "Active" },
    { name: "Himalayas & RemoteOK APIs", count: 360, icon: "🏔️", speed: "28 req/s", status: "Active" },
    { name: "ATS Harvester (Lever, Greenhouse, SmartRecruiters)", count: 284, icon: "⚡", speed: "65 req/s", status: "Active" },
    { name: "WeWorkRemotely, NoDesk, Jobicy & The Muse", count: 220, icon: "🌐", speed: "30 req/s", status: "Active" },
  ];

  return (
    <div style={containerStyle}>
      {/* Header Pill */}
      <div
        style={{
          transform: `scale(${titleSpring})`,
          opacity: titleSpring,
          backgroundColor: THEME.emeraldLight,
          border: `1.5px solid ${THEME.emeraldBorder}`,
          color: THEME.emerald,
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
        <span
          style={{
            width: "10px",
            height: "10px",
            borderRadius: "50%",
            backgroundColor: THEME.emerald,
            display: "inline-block",
            boxShadow: "0 0 10px rgba(5, 150, 105, 0.8)",
          }}
        />
        Live Multi-Threaded Harvester
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
        Ingesting <span style={{ color: THEME.blue }}>10+ Sources</span> Simultaneously
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
        Zero bot blockers. Headless browser fallback. Direct REST and RSS stream normalization.
      </p>

      {/* Big Counter Banner Card */}
      <div
        style={{
          width: "100%",
          maxWidth: "840px",
          backgroundColor: THEME.cardBg,
          borderRadius: "20px",
          padding: "24px 32px",
          border: `1.5px solid ${THEME.cardBorder}`,
          boxShadow: THEME.cardShadow,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "20px",
          transform: `scale(${titleSpring})`,
        }}
      >
        <div>
          <div style={{ fontSize: "16px", fontWeight: 700, color: THEME.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Total Fresh Jobs Parsed (Last 24h)
          </div>
          <div
            style={{
              fontSize: "56px",
              fontWeight: 900,
              color: THEME.blue,
              letterSpacing: "-0.04em",
              fontFamily: "'JetBrains Mono', monospace",
              marginTop: "4px",
            }}
          >
            {liveCount.toLocaleString()}{" "}
            <span style={{ fontSize: "24px", color: THEME.emerald, fontWeight: 700 }}>+ Live Sync</span>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "8px", alignItems: "flex-end" }}>
          <div
            style={{
              padding: "6px 14px",
              backgroundColor: THEME.emeraldLight,
              color: THEME.emerald,
              borderRadius: "8px",
              fontWeight: 700,
              fontSize: "15px",
              border: `1px solid ${THEME.emeraldBorder}`,
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: THEME.emerald }} />
            44 Workers Running
          </div>
          <div style={{ fontSize: "14px", color: THEME.textMuted }}>Avg Cycle: 38.4 seconds</div>
        </div>
      </div>

      {/* Source Rows */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "12px",
          width: "100%",
          maxWidth: "840px",
        }}
      >
        {sources.map((src, i) => {
          const rowSpring = spring({
            frame: frame - 15 - i * 12,
            fps,
            config: { damping: 14, mass: 0.7, stiffness: 120 },
          });

          const currentCount = Math.floor(
            interpolate(frame - 15 - i * 12, [0, 45], [0, src.count], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })
          );

          return (
            <div
              key={src.name}
              style={{
                transform: `translateX(${interpolate(rowSpring, [0, 1], [-30, 0])}px) scale(${rowSpring})`,
                opacity: rowSpring,
                backgroundColor: THEME.cardBg,
                borderRadius: "14px",
                padding: "16px 22px",
                border: `1px solid ${THEME.cardBorder}`,
                boxShadow: "0 4px 15px rgba(0,0,0,0.03)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                <span style={{ fontSize: "24px" }}>{src.icon}</span>
                <span style={{ fontSize: "18px", fontWeight: 700, color: THEME.textPrimary }}>
                  {src.name}
                </span>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "20px" }}>
                <span
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: "18px",
                    fontWeight: 700,
                    color: THEME.blue,
                  }}
                >
                  {currentCount} jobs
                </span>
                <span
                  style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: THEME.textMuted,
                    backgroundColor: THEME.bg,
                    padding: "4px 10px",
                    borderRadius: "6px",
                  }}
                >
                  {src.speed}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
