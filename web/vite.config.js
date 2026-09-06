import { resolve } from "node:path";
import { defineConfig } from "vite";

// Multi-page: launcher + playground (with 3D sword) + game.
export default defineConfig({
  root: __dirname,
  server: { port: 5173, open: false },
  build: {
    rollupOptions: {
      input: {
        index: resolve(__dirname, "index.html"),
        playground: resolve(__dirname, "playground.html"),
        game: resolve(__dirname, "game.html"),
      },
    },
  },
});
