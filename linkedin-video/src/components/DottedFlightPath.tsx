import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

export const DottedFlightPath: React.FC<{
  startX?: number;
  startY?: number;
  endX?: number;
  endY?: number;
  progress?: number;
}> = ({
  startX = -100,
  startY = 400,
  endX = 1180,
  endY = 300,
  progress = 0.5,
}) => {
  const curX = startX + (endX - startX) * progress;
  const curY = startY + (endY - startY) * progress - Math.sin(progress * Math.PI) * 120;
  
  // Calculate flight angle
  const angle = Math.atan2(endY - startY, endX - startX) * (180 / Math.PI) - Math.cos(progress * Math.PI) * 20;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 4 }}>
      {/* Flight Path SVG Line */}
      <svg width="1080" height="1350" style={{ position: "absolute", inset: 0 }}>
        <path
          d={`M ${startX} ${startY} Q ${(startX + endX) / 2} ${(startY + endY) / 2 - 140} ${endX} ${endY}`}
          fill="none"
          stroke="rgba(37, 99, 235, 0.35)"
          strokeWidth="3.5"
          strokeDasharray="10 10"
        />
      </svg>

      {/* Paper Plane Mark Flying along the path */}
      <div
        style={{
          position: "absolute",
          left: `${curX}px`,
          top: `${curY}px`,
          transform: `translate(-50%, -50%) rotate(${angle}deg)`,
          width: "48px",
          height: "48px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          filter: "drop-shadow(0 4px 10px rgba(37, 99, 235, 0.3))",
        }}
      >
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
          <path
            d="M2 12L22 2L12 22L10 13L2 12Z"
            fill="#2563EB"
            stroke="#FFFFFF"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    </div>
  );
};
