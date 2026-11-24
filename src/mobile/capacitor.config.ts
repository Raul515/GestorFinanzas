import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.gestorfinanzas.mobile",
  appName: "Gestor Finanzas",
  webDir: "dist-apk",
  server: {
    androidScheme: "https",
    cleartext: true,
  },
  android: {
    allowMixedContent: true,
    captureInput: true,
    adjustMarginsForEdgeToEdge: "auto",
  },
};

export default config;
