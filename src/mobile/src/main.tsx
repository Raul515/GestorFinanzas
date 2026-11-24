import React from "react";
import ReactDOM from "react-dom/client";
import { Capacitor } from "@capacitor/core";
import App from "./App";
import "./index.css";

const rootElement = document.getElementById("root");
if (rootElement) {
  ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

// Registro de Service Worker únicamente en entorno Web PWA (omitido en APK nativa Capacitor y Vite dev)
const isNativeCapacitor =
  Capacitor.isNativePlatform() ||
  window.location.protocol === "capacitor:" ||
  window.location.protocol === "file:";

if ("serviceWorker" in navigator && !isNativeCapacitor && !window.location.host.includes("5173")) {
  const hadSwController = !!navigator.serviceWorker.controller;
  let swRefreshing = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    const activeTag = (document.activeElement?.tagName || "").toUpperCase();
    const isEditing = activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT";
    if (hadSwController && !swRefreshing && !isEditing) {
      swRefreshing = true;
      window.location.reload();
    }
  });

  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/mobile/sw.js", { updateViaCache: "none" })
      .then((reg) => reg.update().catch(() => {}))
      .catch(console.error);
  });
}
