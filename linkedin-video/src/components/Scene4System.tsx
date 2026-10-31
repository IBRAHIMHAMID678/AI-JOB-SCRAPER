import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

export const Scene4System: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Phase 1: 0 - 65 frames -> 10 glass chips orbit into funnel
  // Counter climbing to 12,140
  const counterVal = Math.floor(
    interpolate(frame, [0, 55], [420, 12140], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  const chips = [
    { name: "LinkedIn", angle: 0 },
    { name: "Indeed", angle: 36 },
    { name: "Himalayas", angle: 72 },
    { name: "Remotive", angle: 108 },
    { name: "RemoteOK", angle: 144 },
    { name: "WeWorkRemotely", angle: 180 },
    { name: "Jobicy", angle: 216 },
    { name: "The Muse", angle: 252 },
    { name: "Arbeitnow", angle: 288 },
    { name: "Working Nomads", angle: 324 },
  ];

  // Funnel absorption progress
  const absorbProgress = interpolate(frame, [10, 60], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Phase 2: Frame 60+ -> Funnel releases ONE hero card
  const heroCardSpring = spring({
    frame: frame - 60,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 120 },
  });

  // Camera push-in scale from frame 80 to 145
  const cameraPush = interpolate(frame, [80, 140], [1.0, 1.15], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Score ring animation: 34% -> 84% -> 94%
  const scoreVal = Math.floor(
    interpolate(frame, [85, 110, 135], [34, 84, 94], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  // 4 rows ticking green
  const row1 = frame >= 95;
  const row2 = frame >= 108;
  const row3 = frame >= 120;
  const row4 = frame >= 132;

  // Phase 3: Frame 142+ -> AUTO-APPROVED stamp slam
  const stampSpring = spring({
    frame: frame - 142,
    fps,
    config: { damping: 8, mass: 0.4, stiffness: 220 },
  });

  // Camera shake on stamp impact (f142 to f155)
  const shakeX = frame >= 142 && frame < 155 ? (Math.sin(frame * 3.5) * 6 * (1 - (frame - 142) / 13)) : 0;
  const shakeY = frame >= 142 && frame < 155 ? (Math.cos(frame * 4.2) * 5 * (1 - (frame - 142) / 13)) : 0;

  // Shockwave expansion
  const shockwaveScale = interpolate(frame - 142, [0, 25], [0.6, 2.2], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const shockwaveOpacity = interpolate(frame - 142, [0, 20], [0.8, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Falling rejected cards in blurred background
  const rejectedFall = interpolate(frame, [142, 178], [0, 400], {
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
        transform: `translate(${shakeX}px, ${shakeY}px) scale(${cameraPush})`,
      }}
    >
      {/* 1. Orbiting 10 Source Chips and Funnel (Frames 0 - 70) */}
      {frame < 75 && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* Central Glass Funnel Ring */}
          <div
            style={{
              width: "280px",
              height: "280px",
              borderRadius: "50%",
              backgroundColor: "rgba(255, 255, 255, 0.85)",
              border: "3px solid rgba(37, 99, 235, 0.4)",
              boxShadow: "0 0 60px rgba(37, 99, 235, 0.25), inset 0 0 40px rgba(37, 99, 235, 0.15)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 3,
            }}
          >
            <div style={{ fontSize: "18px", fontWeight: 800, color: "#2563EB", letterSpacing: "0.08em" }}>
              INGESTING
            </div>
            <div
              style={{
                fontSize: "44px",
                fontWeight: 900,
                color: "#0B0F1A",
                fontVariantNumeric: "tabular-nums",
                marginTop: "4px",
              }}
            >
              {counterVal.toLocaleString()}
            </div>
          </div>

          {/* 10 Orbiting Source Chips */}
          {chips.map((chip, i) => {
            const rad = (chip.angle * Math.PI) / 180;
            const dist = interpolate(absorbProgress, [0, 1], [420, 110]);
            const chipX = Math.cos(rad + frame * 0.04) * dist;
            const chipY = Math.sin(rad + frame * 0.04) * dist;
            const chipScale = interpolate(absorbProgress, [0, 0.8, 1], [1, 0.9, 0]);

            return (
              <div
                key={chip.name}
                style={{
                  position: "absolute",
                  transform: `translate(${chipX}px, ${chipY}px) scale(${chipScale})`,
                  backgroundColor: "rgba(255, 255, 255, 0.9)",
                  border: "1.5px solid rgba(255, 255, 255, 0.95)",
                  boxShadow: "0 15px 35px rgba(11, 15, 26, 0.08)",
                  borderRadius: "999px",
                  padding: "10px 22px",
                  fontSize: "18px",
                  fontWeight: 800,
                  color: "#0B0F1A",
                  zIndex: 4,
                  whiteSpace: "nowrap",
                }}
              >
                {chip.name}
              </div>
            );
          })}
        </div>
      )}

      {/* 2. Blurry Falling Rejected Cards (Frame 142+) */}
      {frame >= 142 && (
        <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1 }}>
          <div
            style={{
              position: "absolute",
              top: `${200 + rejectedFall}px`,
              left: "120px",
              width: "220px",
              padding: "16px",
              backgroundColor: "rgba(255, 255, 255, 0.5)",
              borderRadius: "20px",
              border: "1px solid rgba(220, 38, 38, 0.3)",
              filter: "blur(6px)",
              opacity: 1 - rejectedFall / 400,
            }}
          >
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#DC2626" }}>REJECTED: US-ONLY</div>
          </div>
          <div
            style={{
              position: "absolute",
              top: `${260 + rejectedFall * 1.2}px`,
              right: "120px",
              width: "220px",
              padding: "16px",
              backgroundColor: "rgba(255, 255, 255, 0.5)",
              borderRadius: "20px",
              border: "1px solid rgba(220, 38, 38, 0.3)",
              filter: "blur(7px)",
              opacity: 1 - rejectedFall / 400,
            }}
          >
            <div style={{ fontSize: "14px", fontWeight: 700, color: "#DC2626" }}>REJECTED: 8+ YOE</div>
          </div>
        </div>
      )}

      {/* 3. The Hero Job Card (Emerges from frame 60) */}
      {frame >= 60 && (
        <div
          style={{
            transform: `scale(${heroCardSpring})`,
            opacity: heroCardSpring,
            width: "820px",
            backgroundColor: "rgba(255, 255, 255, 0.88)",
            backdropFilter: "blur(32px)",
            border: "2px solid rgba(255, 255, 255, 0.98)",
            borderRadius: "36px",
            boxShadow: "0 40px 80px -15px rgba(11, 15, 26, 0.15), 0 0 1px rgba(11, 15, 26, 0.18)",
            padding: "48px",
            position: "relative",
            zIndex: 10,
          }}
        >
          {/* Header Row: Title + Score Ring */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "36px",
            }}
          >
            <div>
              <div
                style={{
                  fontSize: "48px",
                  lineHeight: "1.1",
                  fontWeight: 900,
                  letterSpacing: "-0.04em",
                  color: "#0B0F1A",
                }}
              >
                Junior AI & Full-Stack Engineer
              </div>
              <div style={{ fontSize: "28px", color: "#64748B", fontWeight: 600, marginTop: "6px" }}>
                Worldwide Remote • Series A
              </div>
            </div>

            {/* Score Ring */}
            <div
              style={{
                width: "130px",
                height: "130px",
                borderRadius: "50%",
                background: "conic-gradient(#16A34A 0deg, #16A34A calc(var(--deg)), #E2E8F0 calc(var(--deg)), #E2E8F0 360deg)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                position: "relative",
                border: "4px solid rgba(255,255,255,0.9)",
                boxShadow: "0 10px 25px rgba(22, 163, 74, 0.2)",
              }}
            >
              <div
                style={{
                  width: "105px",
                  height: "105px",
                  borderRadius: "50%",
                  backgroundColor: "#FFFFFF",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "36px",
                  fontWeight: 900,
                  color: "#16A34A",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {scoreVal}%
              </div>
            </div>
          </div>

          {/* 4 Rows Ticking Green */}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {[
              { label: "Tech Stack Fit", detail: "Python, FastAPI, React, RAG", active: row1 },
              { label: "Location", detail: "Worldwide Remote Verified", active: row2 },
              { label: "Experience", detail: "0-2 Years (Junior Friendly)", active: row3 },
              { label: "Salary", detail: "$75K - $110K USD", active: row4 },
            ].map((row, i) => (
              <div
                key={row.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "16px 24px",
                  borderRadius: "18px",
                  backgroundColor: row.active ? "rgba(22, 163, 74, 0.08)" : "rgba(241, 245, 249, 0.6)",
                  border: `1.5px solid ${row.active ? "rgba(22, 163, 74, 0.25)" : "rgba(226, 232, 240, 0.8)"}`,
                  transition: "all 0.2s ease",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                  <span
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "50%",
                      backgroundColor: row.active ? "#16A34A" : "#CBD5E1",
                      color: "#FFFFFF",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "18px",
                      fontWeight: 900,
                    }}
                  >
                    {row.active ? "✓" : "·"}
                  </span>
                  <span style={{ fontSize: "24px", fontWeight: 800, color: "#0B0F1A" }}>{row.label}</span>
                </div>
                <span style={{ fontSize: "20px", fontWeight: 700, color: row.active ? "#16A34A" : "#64748B" }}>
                  {row.detail}
                </span>
              </div>
            ))}
          </div>

          {/* 4. Shockwave Ripple */}
          {frame >= 142 && (
            <div
              style={{
                position: "absolute",
                top: "50%",
                left: "50%",
                width: "400px",
                height: "400px",
                transform: `translate(-50%, -50%) scale(${shockwaveScale})`,
                borderRadius: "50%",
                border: "4px solid #16A34A",
                opacity: shockwaveOpacity,
                pointerEvents: "none",
                zIndex: 15,
              }}
            />
          )}

          {/* 5. AUTO-APPROVED Stamp Slam */}
          {frame >= 142 && (
            <div
              style={{
                position: "absolute",
                top: "42%",
                left: "50%",
                transform: `translate(-50%, -50%) scale(${stampSpring}) rotate(-7deg)`,
                opacity: stampSpring,
                backgroundColor: "#16A34A",
                color: "#FFFFFF",
                padding: "24px 64px",
                borderRadius: "28px",
                fontSize: "52px",
                fontWeight: 900,
                letterSpacing: "0.08em",
                boxShadow: "0 25px 60px rgba(22, 163, 74, 0.5), 0 0 1px rgba(255, 255, 255, 0.9)",
                border: "4px solid #FFFFFF",
                display: "flex",
                alignItems: "center",
                gap: "20px",
                zIndex: 20,
              }}
            >
              <span>✓</span> AUTO-APPROVED
            </div>
          )}
        </div>
      )}
    </div>
  );
};
