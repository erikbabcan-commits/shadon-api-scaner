import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }: { mode: string }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxyTarget = env.VITE_DEV_API_PROXY || "http://127.0.0.1:8000";

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["favicon.svg", "offline.html", "pwa-192.png", "pwa-512.png"],
        manifest: {
          name: "Stráž — Bezpečnostný Monitoring",
          short_name: "Stráž",
          description: "Monitoring vlastných aplikácií a infraštruktúry",
          theme_color: "#0f172a",
          background_color: "#0f172a",
          display: "standalone",
          start_url: "/",
          icons: [
            { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
            {
              src: "pwa-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "any maskable",
            },
          ],
          shortcuts: [
            {
              name: "Prehľad",
              short_name: "Prehľad",
              description: "Hlavný dashboard monitoringu",
              url: "/",
              icons: [{ src: "pwa-192.png", sizes: "192x192" }],
            },
            {
              name: "Aplikácie",
              short_name: "Aplikácie",
              description: "Zoznam monitorovaných aplikácií",
              url: "/apps",
              icons: [{ src: "pwa-192.png", sizes: "192x192" }],
            },
            {
              name: "Nálezy",
              short_name: "Nálezy",
              description: "Bezpečnostné nálezy a zraniteľnosti",
              url: "/findings",
              icons: [{ src: "pwa-192.png", sizes: "192x192" }],
            },
          ],
        },
        workbox: {
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [/^\/api\//],
          runtimeCaching: [
            {
              urlPattern: ({ url }: { url: URL }) => url.pathname.startsWith("/api/"),
              handler: "NetworkFirst",
              options: {
                cacheName: "straz-api",
                networkTimeoutSeconds: 5,
                expiration: { maxEntries: 50, maxAgeSeconds: 60 * 30 },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
              return "vendor-react";
            }
            if (id.includes("node_modules/@tanstack")) {
              return "vendor-tanstack";
            }
          },
        },
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
