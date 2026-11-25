import { isNativeOrLocalOrigin, normalizeServerUrl } from "../../utils/formatters";

export const STORAGE_KEYS = {
  TRANSACTIONS: "gestor_mobile_transactions",
  CATALOG: "gestor_mobile_catalog",
  SERVER_URL: "gestor_mobile_server_url",
  PAIRING_TOKEN: "gestor_mobile_pairing_token",
  PENDING_DELETES: "gestor_mobile_pending_deletes",
  MONTHLY_SUMMARY: "gestor_mobile_monthly_summary",
  MONTHLY_SUMMARIES_MAP: "gestor_mobile_monthly_summaries_map",
  HISTORY_CACHE: "gestor_mobile_history_cache",
  QUICK_PRESETS: "gestor_mobile_quick_presets",
} as const;

export const getStoredPairingToken = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEYS.PAIRING_TOKEN);
  } catch {
    return null;
  }
};

export const saveStoredPairingToken = (token: string): void => {
  try {
    if (token && token.trim()) {
      localStorage.setItem(STORAGE_KEYS.PAIRING_TOKEN, token.trim());
    }
  } catch (err) {
    console.error("Error guardando token de emparejamiento:", err);
  }
};

export const clearStoredPairingToken = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEYS.PAIRING_TOKEN);
  } catch (err) {
    console.error("Error eliminando token de emparejamiento:", err);
  }
};

export const extractAndSavePairingTokenFromUrl = (): string | null => {
  if (typeof window === "undefined") return null;
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get("token");
    if (tokenFromUrl && tokenFromUrl.trim()) {
      saveStoredPairingToken(tokenFromUrl);
      urlParams.delete("token");
      const newQuery = urlParams.toString();
      const newUrl = window.location.pathname + (newQuery ? `?${newQuery}` : "") + window.location.hash;
      window.history.replaceState({}, document.title, newUrl);
      return tokenFromUrl.trim();
    }
  } catch (err) {
    console.warn("No se pudo inspeccionar el token en la URL:", err);
  }
  return getStoredPairingToken();
};

export const getStoredServerUrl = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEYS.SERVER_URL);
  } catch {
    return null;
  }
};

export const saveStoredServerUrl = (rawUrl: string): string => {
  try {
    const clean = normalizeServerUrl(rawUrl);
    if (clean) {
      localStorage.setItem(STORAGE_KEYS.SERVER_URL, clean);
      return clean;
    }
  } catch (err) {
    console.error("Error guardando URL de servidor:", err);
  }
  return "";
};

export const clearStoredServerUrl = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEYS.SERVER_URL);
  } catch (err) {
    console.error("Error eliminando URL de servidor:", err);
  }
};

export const extractAndSaveServerUrlFromUrl = (): string | null => {
  if (typeof window === "undefined") return null;
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const serverFromParam = urlParams.get("server") || urlParams.get("api");
    if (serverFromParam && serverFromParam.trim()) {
      const saved = saveStoredServerUrl(serverFromParam);
      urlParams.delete("server");
      urlParams.delete("api");
      const newQuery = urlParams.toString();
      const newUrl = window.location.pathname + (newQuery ? `?${newQuery}` : "") + window.location.hash;
      window.history.replaceState({}, document.title, newUrl);
      return saved;
    }

    const existingStored = getStoredServerUrl();
    if (existingStored && existingStored.trim()) {
      return existingStored.trim();
    }

    if (window.location.origin && !isNativeOrLocalOrigin(window.location.origin)) {
      return saveStoredServerUrl(window.location.origin);
    }
  } catch (err) {
    console.warn("No se pudo inspeccionar el servidor en la URL:", err);
  }
  return getStoredServerUrl();
};

export const isIOSDevice = (): boolean => {
  if (typeof navigator === "undefined") return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent || "") ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
};
