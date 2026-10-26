/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // dark mode disabled — always light
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#1d1d1f",
          900: "#2d2d2f",
          800: "#3a3a3c",
          700: "#636366",
          600: "#6e6e73",
          500: "#86868b",
          400: "#aeaeb2",
          300: "#c7c7cc",
          200: "#e5e5ea",
          100: "#f2f2f7",
          50: "#f5f5f7",
        },
        // Keep coral for any existing badge/accent uses — map to Apple blue
        coral: {
          DEFAULT: "#0071e3",
          bright: "#147ce5",
          soft: "#5aabff",
          muted: "#0058ae",
        },
      },
      fontFamily: {
        sans: [
          '"Inter"',
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Text"',
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        serif: [
          '"Inter"',
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Display"',
          '"Helvetica Neue"',
          "sans-serif",
        ],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glass: "0 1px 0 rgba(255,255,255,0.6) inset, 0 4px 16px rgba(0,0,0,0.07)",
        lift: "0 8px 24px rgba(0,0,0,0.08)",
      },
      letterSpacing: {
        tightish: "-0.022em",
      },
    },
  },
  plugins: [],
};
