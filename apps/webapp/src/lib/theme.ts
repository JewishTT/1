// Design tokens — shared across components. PANO visual language
// (CC BY-NC-4.0): bg #1e1e1e, surfaces #2d2d2d/#3d3d3d, borders #404040/#555555,
// action blue #0078d4, danger #d42828, monospace type. Mirrors :root in index.css.
export const theme = {
  colors: {
    background: "#1e1e1e",
    surface: "#2d2d2d",
    surfaceHover: "#3d3d3d",
    border: "#404040",
    borderHover: "#555555",
    text: "#ffffff",
    textMuted: "#b4b4b4",
    textDim: "#969696",
    primary: "#0078d4",
    primaryHover: "#1084d8",
    accent: "#63aef5",
    accentHover: "#78b9f7",
    warning: "#e6c15c",
    danger: "#e05555",
    dangerHover: "#ee6060",
    success: "#58d68d",
    info: "#63aef5",
    shadow: "rgba(0,0,0,0.5)",
  },
  gradients: {
    primary: "linear-gradient(135deg, #0078d4 0%, #63aef5 100%)",
  },
  spacing: {
    xs: "0.25rem",
    sm: "0.5rem",
    md: "0.75rem",
    lg: "1rem",
    xl: "1.25rem",
    "2xl": "1.75rem",
    "3xl": "2.25rem",
    "4xl": "3rem",
  },
typography: {
    family:
      "'Geist Mono', 'Cascadia Mono', 'JetBrains Mono', 'SF Mono', Consolas, monospace",
    size: {
      xs: "0.75rem",
      sm: "0.875rem",
      base: "1rem",
      lg: "1.125rem",
      xl: "1.25rem",
      "2xl": "1.5rem",
      "3xl": "1.875rem",
      "4xl": "2.25rem",
    },
    weight: {
      normal: "400",
      medium: "500",
      semibold: "600",
      bold: "700",
      black: "900",
    },
  },
  radii: {
    sm: "0.25rem",
    md: "0.5rem",
    lg: "0.75rem",
    xl: "1rem",
    xl2: "1.25rem",
    full: "9999px",
  },
  shadows: {
    sm: "0 1px 2px rgba(0,0,0,0.05)",
    md: "0 4px 6px rgba(0,0,0,0.1)",
    lg: "0 10px 15px rgba(0,0,0,0.2)",
    xl: "0 20px 25px rgba(0,0,0,0.3)",
  },
  layout: {
    sidebarWidth: "260px",
    headerHeight: "60px",
  },
} as const;

export type Theme = typeof theme;
export default theme;
