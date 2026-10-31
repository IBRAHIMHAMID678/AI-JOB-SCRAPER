import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { JobPilotLogo } from "./JobPilotLogo";

export const Scene5Control: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Camera orbit angle across 120 frames
  const orbitY = interpolate(frame, [0, 120], [-4, 4]);
  const orbitX = interpolate(frame, [0, 120], [3, -2]);

  // Main Container Spring
  const mainSpring = spring({
    frame,
    fps,
    config: { damping: 13, mass: 0.7, stiffness: 120 },
  });

  // Four tiles popping in on beats
  const tile1 = spring({ frame: frame - 12, fps, config: { damping: 12, mass: 0.5, stiffness: 140 } });
  const tile2 = spring({ frame: frame - 32, fps, config: { damping: 12, mass: 0.5, stiffness: 140 } });
  const tile3 = spring({ frame: frame - 52, fps, config: { damping: 12, mass: 0.5, stiffness: 140 } });
  const tile4 = spring({ frame: frame - 72, fps, config: { damping: 12, mass: 0.5, stiffness: 140 } });

  // Count-up values
  const count1 = Math.floor(interpolate(frame, [12, 45], [0, 4820], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const count3 = Math.floor(interpolate(frame, [52, 85], [0, 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));

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
        padding: "60px 80px",
        boxSizing: "border-box",
        fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif",
        perspective: "1200px",
      }}
    >
      {/* 3D Dashboard Panel filling >60% of frame */}
      <div
        style={{
          transform: `scale(${mainSpring}) rotateY(${orbitY}deg) rotateX(${orbitX}deg)`,
          opacity: mainSpring,
          width: "920px",
          height: "920px",
          backgroundColor: "rgba(255, 255, 255, 0.94)",
          border: "2px solid rgba(255, 255, 255, 0.98)",
          borderRadius: "44px",
          boxShadow: "0 40px 90px -20px rgba(11, 15, 26, 0.15)",
          padding: "48px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          transformStyle: "preserve-3d",
        }}
      >
        {/* Header Bar */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <JobPilotLogo size={56} showWordmark={true} />
          <div
            style={{
              padding: "10px 24px",
              backgroundColor: "rgba(22, 163, 74, 0.12)",
              color: "#16A34A",
              borderRadius: "999px",
              fontSize: "22px",
              fontWeight: 800,
            }}
          >
            ● Autopilot Active
          </div>
        </div>

        {/* 4 Large Tiles (Filling frame, readable text >= 40px) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "28px",
            marginTop: "24px",
            flex: 1,
          }}
        >
          {/* Tile 1: "Ghost jobs removed" */}
          <div
            style={{
              transform: `scale(${tile1})`,
              opacity: tile1,
              backgroundColor: "rgba(254, 226, 226, 0.6)",
              border: "2px solid rgba(254, 202, 202, 0.8)",
              borderRadius: "32px",
              padding: "36px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: "56px" }}>👻</span>
            <div>
              <div style={{ fontSize: "56px", fontWeight: 900, color: "#DC2626", fontVariantNumeric: "tabular-nums" }}>
                {count1.toLocaleString()}
              </div>
              <div style={{ fontSize: "40px", fontWeight: 800, color: "#0B0F1A", lineHeight: "1.1", marginTop: "8px" }}>
                Ghost jobs removed
              </div>
            </div>
          </div>

          {/* Tile 2: "Fits your experience" */}
          <div
            style={{
              transform: `scale(${tile2})`,
              opacity: tile2,
              backgroundColor: "rgba(237, 233, 254, 0.6)",
              border: "2px solid rgba(221, 214, 254, 0.8)",
              borderRadius: "32px",
              padding: "36px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: "56px" }}>🎯</span>
            <div>
              <div style={{ fontSize: "56px", fontWeight: 900, color: "#7C3AED" }}>
                100%
              </div>
              <div style={{ fontSize: "40px", fontWeight: 800, color: "#0B0F1A", lineHeight: "1.1", marginTop: "8px" }}>
                Fits your experience
              </div>
            </div>
          </div>

          {/* Tile 3: "Region-checked" */}
          <div
            style={{
              transform: `scale(${tile3})`,
              opacity: tile3,
              backgroundColor: "rgba(209, 250, 229, 0.6)",
              border: "2px solid rgba(167, 243, 208, 0.8)",
              borderRadius: "32px",
              padding: "36px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: "56px" }}>🌍</span>
            <div>
              <div style={{ fontSize: "56px", fontWeight: 900, color: "#16A34A" }}>
                Verified
              </div>
              <div style={{ fontSize: "40px", fontWeight: 800, color: "#0B0F1A", lineHeight: "1.1", marginTop: "8px" }}>
                Region-checked
              </div>
            </div>
          </div>

          {/* Tile 4: "One-click reports" */}
          <div
            style={{
              transform: `scale(${tile4})`,
              opacity: tile4,
              backgroundColor: "rgba(255, 237, 213, 0.6)",
              border: "2px solid rgba(254, 215, 170, 0.8)",
              borderRadius: "32px",
              padding: "36px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: "56px" }}>⚡</span>
            <div>
              <div style={{ fontSize: "56px", fontWeight: 900, color: "#EA580C" }}>
                1-Click
              </div>
              <div style={{ fontSize: "40px", fontWeight: 800, color: "#0B0F1A", lineHeight: "1.1", marginTop: "8px" }}>
                One-click reports
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
