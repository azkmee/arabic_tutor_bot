import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages serves at /<repo-name>/ by default. Override with
// VITE_BASE_PATH for custom domains or different repo names.
const base = process.env.VITE_BASE_PATH ?? "/arabic_tutor_bot/";

export default defineConfig({
  plugins: [react()],
  base,
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
