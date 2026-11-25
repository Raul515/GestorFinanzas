import fs from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const pkg = JSON.parse(fs.readFileSync(new URL("./package.json", import.meta.url), "utf-8"));

const injectPwaHeadTags = () => ({
  name: "inject-pwa-head-tags",
  transformIndexHtml(html: string) {
    const pwaTags =
      '    <link rel="manifest" href="/mobile/manifest.json" />\n    <link rel="apple-touch-icon" href="/mobile/icon-192.png" />\n';
    return html.replace("  </head>", `${pwaTags}  </head>`);
  },
});

export default defineConfig(({ mode }: { mode: string }) => {
  const isPwa = mode === "pwa";
  return {
    plugins: isPwa ? [react(), injectPwaHeadTags()] : [react()],
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version || "1.4.0"),
    },
    base: isPwa ? "/mobile/" : "./",
    publicDir: isPwa ? "public-pwa" : false,
    server: {
      port: 5173,
      host: true,
    },
    build: {
      outDir: isPwa ? "dist" : "dist-apk",
      emptyOutDir: true,
    },
  };
});
