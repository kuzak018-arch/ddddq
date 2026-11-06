import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// @ts-expect-error type error without @types/node package
import process from "node:process";
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig(() => ({
  plugins: [react()],
  // the demo as a claude.ai page: that host serves fonts only from Google Fonts or inline, so the
  // fonts go into the CSS as data URIs (VITE_DEMO_INLINE_FONTS=1; the app and GitHub Pages keep files)
  build: process.env.VITE_DEMO_INLINE_FONTS === "1"
    ? { assetsInlineLimit: (file: string) => (/\.(woff2?|ttf|otf)$/.test(file) ? true : undefined) }
    : undefined,

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },
}));
