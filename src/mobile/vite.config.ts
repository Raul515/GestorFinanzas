import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const mobileRootDir = path.dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(fs.readFileSync(path.join(mobileRootDir, "package.json"), "utf-8"));
const appVersion = String(pkg.version || "1.4.0");

const collectDistAssets = (rootDir: string, currentDir = rootDir): string[] => {
  const entries = fs.readdirSync(currentDir, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const absPath = path.join(currentDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectDistAssets(rootDir, absPath));
    } else if (entry.isFile() && entry.name !== "sw.js") {
      const relPosix = path.relative(rootDir, absPath).split(path.sep).join("/");
      files.push(`/mobile/${relPosix}`);
    }
  }
  return files;
};

const injectPwaHeadTags = () => ({
  name: "inject-pwa-head-tags",
  transformIndexHtml(html: string) {
    const pwaTags =
      '    <link rel="manifest" href="/mobile/manifest.json" />\n    <link rel="apple-touch-icon" href="/mobile/icon-192.png" />\n';
    return html.replace("  </head>", `${pwaTags}  </head>`);
  },
});

const injectSwPrecacheManifest = () => ({
  name: "inject-sw-precache-manifest",
  closeBundle() {
    const distDir = path.resolve(mobileRootDir, "dist");
    const swPath = path.join(distDir, "sw.js");
    if (!fs.existsSync(swPath)) {
      return;
    }

    const assetUrls = Array.from(new Set(["/mobile/", ...collectDistAssets(distDir)])).sort();
    const hasher = crypto.createHash("sha256");
    for (const url of assetUrls) {
      hasher.update(url);
      if (url !== "/mobile/") {
        const rel = url.replace(/^\/mobile\//, "");
        const filePath = path.join(distDir, rel);
        if (fs.existsSync(filePath)) {
          hasher.update(fs.readFileSync(filePath));
        }
      }
    }
    const buildHash = hasher.digest("hex").slice(0, 10);
    const cacheName = `gestor-finanzas-mobile-v${appVersion}-${buildHash}`;

    let swContent = fs.readFileSync(swPath, "utf-8");
    swContent = swContent
      .replace(
        /const CACHE_NAME = .*\/\/ __SW_CACHE_NAME_MARKER__/,
        `const CACHE_NAME = ${JSON.stringify(cacheName)};`
      )
      .replace(
        /const ASSETS_TO_CACHE = .*\/\/ __SW_ASSETS_MARKER__/,
        `const ASSETS_TO_CACHE = ${JSON.stringify(assetUrls, null, 2)};`
      );
    fs.writeFileSync(swPath, swContent, "utf-8");
  },
});

export default defineConfig(({ mode }: { mode: string }) => {
  const isPwa = mode === "pwa";
  return {
    plugins: isPwa ? [react(), injectPwaHeadTags(), injectSwPrecacheManifest()] : [react()],
    define: {
      __APP_VERSION__: JSON.stringify(appVersion),
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
