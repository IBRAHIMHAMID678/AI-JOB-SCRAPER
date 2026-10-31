import React from "react";
import { interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

export const JobPilotMesh: React.FC<{ activeColor?: string }> = ({ activeColor }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Determine dynamic background pastel colors based on storyboard frame timeline
  // 0 - 90: Sky Blue (#DBEAFE)
  // 90 - 120: Soft Rose (#FFE4E6)
  // 120 - 150: Peach/Amber (#FFEDD5)
  // 150 - 180: Lilac (#EDE9FE)
  // 180 - 240: Sky Blue (#DBEAFE)
  // 240 - 292: Mint (#D1FAE5) (Nurse)
  // 292 - 345: Lilac (#EDE9FE) (Designer)
  // 345 - 398: Peach (#FFEDD5) (Accountant)
  // 398 - 450: Sky Blue (#DBEAFE) (Sales)
  // 450 - 570: Mint/Cyan (#CCFBF1) (Control)
  // 570 - 660: Warm Golden (#FEF3C7) (Payoff)
  // 660 - 720: Sky Blue (#DBEAFE) (CTA - loops to start)

  let primaryPastel = "rgba(219, 234, 254, 0.8)"; // Sky blue
  let secondaryPastel = "rgba(237, 233, 254, 0.6)";

  if (frame >= 90 && frame < 120) {
    primaryPastel = "rgba(255, 228, 230, 0.85)"; // Soft Rose
    secondaryPastel = "rgba(254, 205, 211, 0.6)";
  } else if (frame >= 120 && frame < 150) {
    primaryPastel = "rgba(255, 237, 213, 0.85)"; // Peach
    secondaryPastel = "rgba(254, 215, 170, 0.6)";
  } else if (frame >= 150 && frame < 180) {
    primaryPastel = "rgba(237, 233, 254, 0.85)"; // Lilac
    secondaryPastel = "rgba(221, 214, 254, 0.6)";
  } else if (frame >= 180 && frame < 240) {
    primaryPastel = "rgba(219, 234, 254, 0.85)"; // Sky blue
    secondaryPastel = "rgba(191, 219, 254, 0.6)";
  } else if (frame >= 240 && frame < 292) {
    primaryPastel = "rgba(209, 250, 229, 0.85)"; // Mint (Nurse)
    secondaryPastel = "rgba(167, 243, 208, 0.6)";
  } else if (frame >= 292 && frame < 345) {
    primaryPastel = "rgba(237, 233, 254, 0.85)"; // Lilac (Designer)
    secondaryPastel = "rgba(221, 214, 254, 0.6)";
  } else if (frame >= 345 && frame < 398) {
    primaryPastel = "rgba(255, 237, 213, 0.85)"; // Peach (Accountant)
    secondaryPastel = "rgba(254, 215, 170, 0.6)";
  } else if (frame >= 398 && frame < 450) {
    primaryPastel = "rgba(219, 234, 254, 0.85)"; // Sky blue (Sales)
    secondaryPastel = "rgba(191, 219, 254, 0.6)";
  } else if (frame >= 450 && frame < 570) {
    primaryPastel = "rgba(204, 251, 241, 0.85)"; // Mint/Cyan (Control)
    secondaryPastel = "rgba(153, 246, 228, 0.6)";
  } else if (frame >= 570 && frame < 660) {
    primaryPastel = "rgba(254, 243, 199, 0.9)"; // Golden Sunlight (Payoff)
    secondaryPastel = "rgba(253, 230, 138, 0.65)";
  } else if (frame >= 660) {
    primaryPastel = "rgba(219, 234, 254, 0.85)"; // Sky Blue (CTA)
    secondaryPastel = "rgba(237, 233, 254, 0.6)";
  }

  // Smooth angle for drifting clouds / haze
  const angle = (frame / durationInFrames) * Math.PI * 2;
  const hazeX = 50 + 20 * Math.sin(angle);
  const hazeY = 30 + 15 * Math.cos(angle);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        backgroundColor: "#F8F7F4",
        overflow: "hidden",
        zIndex: 0,
        transition: "background-color 0.4s ease",
      }}
    >
      {/* Dynamic Full-Bleed Primary Pastel Field */}
      <div
        style={{
          position: "absolute",
          width: "1200px",
          height: "1200px",
          borderRadius: "50%",
          left: `${hazeX}%`,
          top: `${hazeY}%`,
          transform: "translate(-50%, -50%)",
          background: `radial-gradient(circle, ${primaryPastel} 0%, rgba(248, 247, 244, 0) 70%)`,
          pointerEvents: "none",
          transition: "background 0.3s ease",
        }}
      />

      {/* Floating Soft Cloud/Flight Haze */}
      <div
        style={{
          position: "absolute",
          width: "900px",
          height: "600px",
          borderRadius: "50%",
          right: "-100px",
          bottom: "100px",
          background: `radial-gradient(ellipse, ${secondaryPastel} 0%, rgba(248, 247, 244, 0) 70%)`,
          pointerEvents: "none",
        }}
      />

      {/* Fine Paper Grain Texture Overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `url(${staticFile("paper_grain.png")})`,
          backgroundRepeat: "repeat",
          opacity: 0.12,
          mixBlendMode: "multiply",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};
