/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--canvas))",
        surface: "hsl(var(--surface))",
        elevated: "hsl(var(--elevated))",
        line: "hsl(var(--line))",
        ink: "hsl(var(--ink))",
        muted: "hsl(var(--muted))",
        cyan: "hsl(var(--cyan))",
        blue: "hsl(var(--blue))",
        good: "hsl(var(--good))",
        warn: "hsl(var(--warn))",
        danger: "hsl(var(--danger))",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--cyan) / .14), 0 8px 30px hsl(var(--cyan) / .08)",
      },
      backgroundImage: {
        "ambient-grid": "linear-gradient(hsl(var(--line) / .18) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--line) / .18) 1px, transparent 1px)",
      },
    },
  },
  plugins: [],
};
