// The sketch panel (DR §9), built into the editor's static files.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

export default defineConfig({
  root: here("./src/sketch"),
  base: "/ui/sketch/",
  plugins: [react()],
  build: {
    outDir: here("../engine/app/ui/sketch"),
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
    // deterministic names: the same source builds the same files
    rollupOptions: { output: { entryFileNames: "assets/sketch.js", chunkFileNames: "assets/[name].js",
                               assetFileNames: "assets/[name][extname]" } },
  },
});
