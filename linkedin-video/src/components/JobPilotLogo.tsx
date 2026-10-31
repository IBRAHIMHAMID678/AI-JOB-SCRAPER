import React from "react";

export const JobPilotLogo: React.FC<{ size?: number; showWordmark?: boolean; textColor?: string }> = ({
  size = 64,
  showWordmark = true,
  textColor = "#0B0F1A",
}) => {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: `${size * 0.35}px` }}>
      {/* Rounded Glass Square with Blue Paper Plane */}
      <div
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: `${size * 0.3}px`,
          backgroundColor: "rgba(255, 255, 255, 0.95)",
          border: "2px solid rgba(255, 255, 255, 0.98)",
          boxShadow: "0 20px 40px -10px rgba(37, 99, 235, 0.22), 0 0 1px rgba(11, 15, 26, 0.15)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <svg
          width={`${size * 0.58}px`}
          height={`${size * 0.58}px`}
          viewBox="0 0 24 24"
          fill="none"
        >
          <path
            d="M2.5 11.5L21.5 2.5L12.5 21.5L10 13L2.5 11.5Z"
            fill="#2563EB"
            stroke="#2563EB"
            strokeWidth="1"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      {/* Wordmark: Job Pilot */}
      {showWordmark && (
        <span
          style={{
            fontSize: `${size * 0.85}px`,
            fontWeight: 900,
            letterSpacing: "-0.04em",
            color: textColor,
            lineHeight: 1,
            fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif",
          }}
        >
          Job Pilot
        </span>
      )}
    </div>
  );
};
