import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { DottedFlightPath } from "./DottedFlightPath";

export const Scene1Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Number count-up: 0 to 12,000 in 1s (30 frames)
  const countProgress = interpolate(frame, [0, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const countVal = Math.floor(countProgress * 12000);

  // Line 1 slam spring
  const slam1 = spring({
    frame,
    fps,
    config: { damping: 12, mass: 0.6, stiffness: 140 },
  });

  // Line 2: "Which ones are real?" appears at frame 36
  const slam2 = spring({
    frame: frame - 36,
    fps,
    config: { damping: 11, mass: 0.5, stiffness: 150 },
  });

  // Word "real" pop in blue
  const popReal = spring({
    frame: frame - 42,
    fps,
    config: { damping: 9, mass: 0.4, stiffness: 190 },
  });

  // Flight path progress across Scene 1
  const flightProgress = interpolate(frame, [10, 85], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Universal job cards swarm covering diverse non-developer fields
  const diverseCards = [
    { title: "Registered Nurse", org: "St. Jude Health", x: -260, y: 320, rot: -8, match: "96%" },
    { title: "Graphic Designer", org: "Studio Pentagram", x: 260, y: 340, rot: 7, match: "94%" },
    { title: "Accountant (CPA)", org: "Deloitte & Co.", x: -280, y: 470, rot: 6, match: "95%" },
    { title: "Sales Manager", org: "HubSpot Enterprise", x: 270, y: 490, rot: -7, match: "93%" },
    { title: "High-School Teacher", org: "Oakridge Academy", x: 0, y: 580, rot: 2, match: "97%" },
    { title: "Master Electrician", org: "Apex Power Grid", x: -240, y: 640, rot: -5, match: "92%" },
    { title: "Customer Support Lead", org: "Shopify Support", x: 240, y: 650, rot: 6, match: "94%" },
  ];

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
      {/* Flight Path with paper plane gliding across */}
      <DottedFlightPath
        startX={-80}
        startY={480}
        endX={1160}
        endY={280}
        progress={flightProgress}
      />

      {/* Swarm of Universal Diverse Job Cards filling lower 60% of frame */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          pointerEvents: "none",
          zIndex: 2,
        }}
      >
        {diverseCards.map((card, i) => {
          const cardSpring = spring({
            frame: frame - 15 - i * 5,
            fps,
            config: { damping: 13, mass: 0.6, stiffness: 130 },
          });
          return (
            <div
              key={card.title}
              style={{
                position: "absolute",
                transform: `translate(${card.x}px, ${card.y}px) rotate(${card.rot}deg) scale(${cardSpring})`,
                opacity: cardSpring,
                width: "360px",
                padding: "20px 24px",
                backgroundColor: "rgba(255, 255, 255, 0.94)",
                border: "2px solid rgba(255, 255, 255, 0.98)",
                borderRadius: "24px",
                boxShadow: "0 20px 45px -10px rgba(11, 15, 26, 0.12)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontSize: "22px", fontWeight: 900, color: "#0B0F1A" }}>
                  {card.title}
                </div>
                <div style={{ fontSize: "16px", color: "#64748B", fontWeight: 700, marginTop: "2px" }}>
                  {card.org}
                </div>
              </div>
              <div
                style={{
                  backgroundColor: "rgba(37, 99, 235, 0.1)",
                  color: "#2563EB",
                  fontSize: "17px",
                  fontWeight: 900,
                  padding: "6px 12px",
                  borderRadius: "10px",
                }}
              >
                {card.match}
              </div>
            </div>
          );
        })}
      </div>

      {/* Main Giant Kinetic Headlines */}
      <div
        style={{
          position: "relative",
          zIndex: 10,
          textAlign: "center",
          marginTop: "-260px",
        }}
      >
        {/* Line 1: "12,000 jobs." */}
        <div
          style={{
            transform: `scale(${slam1})`,
            opacity: slam1,
            fontSize: "135px",
            lineHeight: "1.02",
            fontWeight: 900,
            letterSpacing: "-0.05em",
            color: "#0B0F1A",
            textShadow: "0 4px 30px rgba(11, 15, 26, 0.08)",
          }}
        >
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{countVal.toLocaleString()}</span> jobs.
        </div>

        {/* Line 2: "Which ones are real?" */}
        {frame > 32 && (
          <div
            style={{
              transform: `scale(${slam2})`,
              opacity: slam2,
              fontSize: "110px",
              lineHeight: "1.08",
              fontWeight: 900,
              letterSpacing: "-0.04em",
              color: "#0B0F1A",
              marginTop: "20px",
            }}
          >
            Which ones are{" "}
            <span
              style={{
                display: "inline-block",
                transform: `scale(${popReal})`,
                color: "#2563EB",
                position: "relative",
              }}
            >
              real?
              <span
                style={{
                  position: "absolute",
                  left: "50%",
                  top: "50%",
                  width: "140px",
                  height: "140px",
                  transform: "translate(-50%, -50%)",
                  borderRadius: "50%",
                  background: "radial-gradient(circle, rgba(37, 99, 235, 0.25) 0%, rgba(37, 99, 235, 0) 70%)",
                  pointerEvents: "none",
                  zIndex: -1,
                }}
              />
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
