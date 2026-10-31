export const THEME = {
  bg: "#F8FAFC",
  bgGridDot: "#CBD5E1",
  cardBg: "#FFFFFF",
  cardBorder: "#E2E8F0",
  cardBorderHover: "#CBD5E1",
  cardShadow: "0 20px 45px -10px rgba(15, 23, 42, 0.08), 0 0 1px rgba(15, 23, 42, 0.12)",
  cardShadowHover: "0 25px 50px -12px rgba(15, 23, 42, 0.14)",
  
  // High-contrast typography (NO dark mode gradient slop)
  textPrimary: "#0F172A",
  textSecondary: "#475569",
  textMuted: "#64748B",
  textLight: "#94A3B8",
  
  // Bold high-visibility brand accents
  blue: "#2563EB",
  blueLight: "#EFF6FF",
  blueBorder: "#BFDBFE",
  
  orange: "#EA580C",
  orangeLight: "#FFF7ED",
  orangeBorder: "#FED7AA",
  
  emerald: "#059669",
  emeraldLight: "#ECFDF5",
  emeraldBorder: "#A7F3D0",
  
  crimson: "#DC2626",
  crimsonLight: "#FEF2F2",
  crimsonBorder: "#FECACA",
  
  purple: "#7C3AED",
  purpleLight: "#F5F3FF",
  purpleBorder: "#DDD6FE",
  
  amber: "#D97706",
  amberLight: "#FFFBEB",
  amberBorder: "#FDE68A",
};

export const containerStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  backgroundColor: THEME.bg,
  backgroundImage: `radial-gradient(${THEME.bgGridDot} 1.5px, transparent 1.5px)`,
  backgroundSize: "28px 28px",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  fontFamily: "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
  color: THEME.textPrimary,
  padding: "48px",
  boxSizing: "border-box",
  position: "relative",
  overflow: "hidden",
};
