import React from "react";
import ReactDOM from "react-dom/client";
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

// Registro de Service Worker para capacidades PWA Offline
if ("serviceWorker" in navigator && !window.location.host.includes("5173")) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/mobile/sw.js").catch(console.error);
  });
}
