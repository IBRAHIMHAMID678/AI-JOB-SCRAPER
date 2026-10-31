import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

interface RoleData {
  title: string;
  category: string;
  company: string;
  score: number;
  color: string;
  icon: string;
  skillText: string;
  locationText: string;
  expText: string;
  salaryText: string;
}

const ROLES: RoleData[] = [
  {
    title: "Registered Nurse",
    category: "Healthcare & Clinical",
    company: "St. Jude Hospital Network",
    score: 96,
    color: "#059669",
    icon: "🩺",
    skillText: "BLS, ICU & Patient Care Match",
    locationText: "Metro General Hospital",
    expText: "1-3 Years Verified",
    salaryText: "$88,000 - $115,000 / yr",
  },
  {
    title: "Graphic Designer",
    category: "Brand & Creative",
    company: "Pentagram Design Studio",
    score: 94,
    color: "#7C3AED",
    icon: "🎨",
    skillText: "Figma, Visual Identity, Motion",
    locationText: "Remote / Hybrid Studio",
    expText: "2+ Years Portfolio Approved",
    salaryText: "$78,000 - $95,000 / yr",
  },
  {
    title: "Corporate Accountant",
    category: "Finance & Audit",
    company: "Apex Global Advisory",
    score: 95,
    color: "#EA580C",
    icon: "📊",
    skillText: "GAAP, Financial Auditing, Tax",
    locationText: "Nationwide Remote",
    expText: "CPA / 2-4 Years Certified",
    salaryText: "$85,000 - $108,000 / yr",
  },
  {
    title: "Sales Manager",
    category: "Enterprise Revenue",
    company: "HubSpot Global Partner",
    score: 97,
    color: "#2563EB",
    icon: "💼",
    skillText: "B2B Pipeline, CRM & Closing",
    locationText: "Worldwide Remote",
    expText: "Track Record Verified",
    salaryText: "$95,000 + Commissions",
  },
];

export const Scene4UniversalDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 4 Roles across 210 frames (~52.5 frames each)
  const roleIndex = Math.min(Math.floor(frame / 52.5), 3);
  const roleFrame = frame % 52.5;
  const currentRole = ROLES[roleIndex];

  // Typing animation for search field
  const fullQuery = currentRole.title;
  const charsCount = Math.floor(
    interpolate(roleFrame, [0, 16], [0, fullQuery.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const typedQuery = fullQuery.slice(0, charsCount);

  // Big Card Entrance spring for the current role
  const cardSpring = spring({
    frame: roleFrame - 10,
    fps,
    config: { damping: 13, mass: 0.6, stiffness: 140 },
  });

  // Score ring filling
  const scoreVal = Math.floor(
    interpolate(roleFrame, [12, 36], [40, currentRole.score], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  // 4 rows ticking green
  const row1 = roleFrame >= 16;
  const row2 = roleFrame >= 24;
  const row3 = roleFrame >= 32;
  const row4 = roleFrame >= 40;

  // BEST MATCH Stamp slam
  const stampSpring = spring({
    frame: roleFrame - 40,
    fps,
    config: { damping: 8, mass: 0.4, stiffness: 220 },
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
        padding: "60px 80px",
        boxSizing: "border-box",
        fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif",
      }}
    >
      {/* 1. Universal Search Field (Top Hero Element) */}
      <div
        style={{
          width: "920px",
          height: "100px",
          backgroundColor: "rgba(255, 255, 255, 0.95)",
          border: "2.5px solid rgba(255, 255, 255, 0.98)",
          borderRadius: "32px",
          boxShadow: "0 20px 45px -10px rgba(11, 15, 26, 0.1)",
          display: "flex",
          alignItems: "center",
          padding: "0 36px",
          gap: "24px",
          marginBottom: "28px",
          zIndex: 10,
        }}
      >
        <span style={{ fontSize: "40px" }}>🔍</span>
        <div style={{ flex: 1, fontSize: "48px", fontWeight: 900, color: "#0B0F1A", letterSpacing: "-0.03em" }}>
          {typedQuery}
          <span
            style={{
              display: "inline-block",
              width: "4px",
              height: "44px",
              backgroundColor: "#2563EB",
              marginLeft: "6px",
              verticalAlign: "middle",
              opacity: Math.sin(roleFrame * 0.4) > 0 ? 1 : 0,
            }}
          />
        </div>
        <div
          style={{
            backgroundColor: "rgba(37, 99, 235, 0.12)",
            color: "#2563EB",
            fontSize: "22px",
            fontWeight: 800,
            padding: "10px 22px",
            borderRadius: "999px",
          }}
        >
          {currentRole.icon} Universal Auto-Match
        </div>
      </div>

      {/* 2. Oversized Glass Job Card (Takes up >60% of frame) */}
      <div
        style={{
          transform: `scale(${cardSpring}) translateY(${interpolate(cardSpring, [0, 1], [35, 0])}px)`,
          opacity: cardSpring,
          width: "920px",
          height: "820px",
          backgroundColor: "rgba(255, 255, 255, 0.94)",
          border: "2px solid rgba(255, 255, 255, 0.98)",
          borderRadius: "40px",
          boxShadow: "0 35px 80px -15px rgba(11, 15, 26, 0.15)",
          padding: "52px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          position: "relative",
          zIndex: 5,
        }}
      >
        {/* Card Header: Role Title + Score Ring */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: "24px", fontWeight: 800, color: currentRole.color, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              {currentRole.category}
            </div>
            <div style={{ fontSize: "52px", fontWeight: 900, color: "#0B0F1A", letterSpacing: "-0.04em", marginTop: "4px" }}>
              {currentRole.title}
            </div>
            <div style={{ fontSize: "30px", fontWeight: 700, color: "#64748B", marginTop: "4px" }}>
              {currentRole.company}
            </div>
          </div>

          {/* Large Score Ring */}
          <div
            style={{
              width: "150px",
              height: "150px",
              borderRadius: "50%",
              backgroundColor: "rgba(255, 255, 255, 0.98)",
              border: `6px solid ${currentRole.color}`,
              boxShadow: `0 15px 35px -5px ${currentRole.color}40`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "48px",
              fontWeight: 900,
              color: currentRole.color,
              fontVariantNumeric: "tabular-nums",
              flexShrink: 0,
            }}
          >
            {scoreVal}%
          </div>
        </div>

        {/* 4 Inspection Rows (Text >= 40px) */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {[
            { label: "Skills Match", val: currentRole.skillText, active: row1 },
            { label: "Location OK", val: currentRole.locationText, active: row2 },
            { label: "Experience Fits", val: currentRole.expText, active: row3 },
            { label: "Salary Shown", val: currentRole.salaryText, active: row4 },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "16px 26px",
                borderRadius: "20px",
                backgroundColor: item.active ? "rgba(22, 163, 74, 0.08)" : "rgba(241, 245, 249, 0.7)",
                border: `1.5px solid ${item.active ? "rgba(22, 163, 74, 0.25)" : "rgba(226, 232, 240, 0.9)"}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
                <span
                  style={{
                    width: "38px",
                    height: "38px",
                    borderRadius: "50%",
                    backgroundColor: item.active ? "#16A34A" : "#CBD5E1",
                    color: "#FFFFFF",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "22px",
                    fontWeight: 900,
                  }}
                >
                  {item.active ? "✓" : "·"}
                </span>
                <span style={{ fontSize: "28px", fontWeight: 800, color: "#0B0F1A" }}>{item.label}</span>
              </div>
              <span style={{ fontSize: "24px", fontWeight: 700, color: item.active ? "#16A34A" : "#64748B" }}>
                {item.val}
              </span>
            </div>
          ))}
        </div>

        {/* Glossy Green "BEST MATCH" Stamp Slam */}
        {roleFrame >= 40 && (
          <div
            style={{
              position: "absolute",
              top: "44%",
              left: "50%",
              transform: `translate(-50%, -50%) scale(${stampSpring}) rotate(-8deg)`,
              opacity: stampSpring,
              backgroundColor: "#16A34A",
              color: "#FFFFFF",
              padding: "24px 64px",
              borderRadius: "28px",
              fontSize: "56px",
              fontWeight: 900,
              letterSpacing: "0.06em",
              boxShadow: "0 25px 60px rgba(22, 163, 74, 0.45)",
              border: "4px solid #FFFFFF",
              display: "flex",
              alignItems: "center",
              gap: "20px",
              zIndex: 20,
            }}
          >
            <span>★</span> BEST MATCH
          </div>
        )}
      </div>
    </div>
  );
};
