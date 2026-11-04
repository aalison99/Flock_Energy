import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        installed: { DEFAULT: "#15803d", soft: "#dcfce7" },
        faulty: { DEFAULT: "#b45309", soft: "#fef3c7" },
        decommissioned: { DEFAULT: "#475569", soft: "#e2e8f0" },
      },
    },
  },
  plugins: [],
} satisfies Config;
