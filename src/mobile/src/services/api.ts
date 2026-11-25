import {
  CatalogData,
  HistoricalTransactionItem,
  MobileMonthlySummary,
  MobileTransaction,
  MobileVersionInfo,
  SearchResponse,
  SubcategoryItem,
} from "../types";
import { isNativeOrLocalOrigin, normalizeServerUrl } from "../utils/formatters";
import { getStoredPairingToken, getStoredServerUrl } from "./storage/config";

export const getBaseApiUrl = (): string => {
  const customUrl = getStoredServerUrl();
  if (customUrl) return customUrl;

  if (typeof window !== "undefined" && window.location.origin) {
    const orig = window.location.origin;
    if (!isNativeOrLocalOrigin(orig)) {
      return orig;
    }
  }
  return "http://localhost:8000";
};

export interface TestConnectionResult {
  success: boolean;
  isPaired: boolean;
  message: string;
  statusCode?: number;
}

export interface PairWithPinResult {
  success: boolean;
  pairingToken?: string;
  message: string;
}

const getCommonHeaders = (): Record<string, string> => {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  const token = getStoredPairingToken();
  if (token) {
    headers["X-Mobile-Pairing-Token"] = token;
  }
  return headers;
};

export const fetchWithTimeout = async (
  url: string,
  options: RequestInit = {},
  timeoutMs = 8000
): Promise<Response> => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeoutId);
  }
};

const isAuthError = (status: number): boolean => status === 401 || status === 403;

export const pairWithPin = async (
  targetUrl: string,
  pin: string
): Promise<PairWithPinResult> => {
  const cleanUrl = normalizeServerUrl(targetUrl);
  if (!cleanUrl) {
    return { success: false, message: "La URL del servidor no puede estar vacía" };
  }
  const cleanPin = pin.trim();
  if (!/^\d{6}$/.test(cleanPin)) {
    return { success: false, message: "El PIN debe tener exactamente 6 dígitos numéricos" };
  }

  try {
    const res = await fetchWithTimeout(
      `${cleanUrl}/api/mobile/pair-pin`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ pin: cleanPin, device_name: "Mobile App" }),
      },
      4000
    );

    const data = await res.json().catch(() => ({}));
    if (res.ok && data.success && data.pairing_token) {
      return {
        success: true,
        pairingToken: data.pairing_token,
        message: data.message || "✓ Dispositivo vinculado con éxito.",
      };
    }
    return {
      success: false,
      message: data.detail || data.message || "PIN no válido o caducado.",
    };
  } catch (err) {
    console.warn("Error en pairWithPin:", err);
    return {
      success: false,
      message: "No se pudo conectar con el servidor. Verifica la URL o la red Wi-Fi.",
    };
  }
};

export const testServerConnection = async (
  targetUrl: string,
  token?: string
): Promise<TestConnectionResult> => {
  const cleanUrl = normalizeServerUrl(targetUrl);
  if (!cleanUrl) {
    return { success: false, isPaired: false, message: "La URL del servidor no puede estar vacía" };
  }

  try {
    const headers: Record<string, string> = { Accept: "application/json" };
    const effectiveToken = token !== undefined ? token.trim() : getStoredPairingToken() || "";
    if (effectiveToken) {
      headers["X-Mobile-Pairing-Token"] = effectiveToken;
    }

    const res = await fetchWithTimeout(`${cleanUrl}/api/mobile/status`, { headers }, 3000);

    if (res.ok) {
      const data = await res.json();
      const isPaired = typeof data.authenticated === "boolean" ? data.authenticated : false;
      if (isPaired) {
        return { success: true, isPaired: true, message: "¡Conectado y emparejado con éxito!", statusCode: res.status };
      }
      return {
        success: true,
        isPaired: false,
        message: effectiveToken
          ? "Servidor alcanzado, pero el token no coincide"
          : "Servidor alcanzado, pero falta introducir el token",
        statusCode: res.status,
      };
    }
    if (isAuthError(res.status)) {
      return {
        success: true,
        isPaired: false,
        message: "Acceso denegado: token no coincide con el servidor",
        statusCode: res.status,
      };
    }
    return {
      success: false,
      isPaired: false,
      message: `El servidor respondió con error HTTP ${res.status}`,
      statusCode: res.status,
    };
  } catch (err: any) {
    if (err?.name === "AbortError") {
      return { success: false, isPaired: false, message: "Tiempo de espera agotado (3s). Revisa la IP y la red" };
    }
    console.warn("Error probando conexión con servidor:", err);
    return { success: false, isPaired: false, message: "No se pudo conectar al servidor. Comprueba la IP y la red" };
  }
};

export const fetchCatalog = async (): Promise<CatalogData | null> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/catalog`,
      { headers: getCommonHeaders() },
      5000
    );
    if (!res.ok) {
      console.warn(`Error HTTP ${res.status} al obtener catálogo móvil`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn("Error de red en fetchCatalog:", err);
    return null;
  }
};

export const syncTransactionsWithBackend = async (
  pendingTxs: MobileTransaction[]
): Promise<{
  success: boolean;
  processedCount: number;
  ignoredCount: number;
  isUnauthorized?: boolean;
  isValidationError?: boolean;
  validationDetail?: string;
} | null> => {
  if (pendingTxs.length === 0) {
    return { success: true, processedCount: 0, ignoredCount: 0 };
  }

  const payload = {
    device_id: "mobile-client",
    transactions: pendingTxs.map((t) => ({
      event_id: t.event_id,
      scope: t.scope,
      type: t.type || "EXPENSE",
      amount: t.amount,
      description: t.description,
      date: t.date,
      subcategory_id: t.subcategory_id,
      subcategory_name: t.subcategory_name,
      created_at_utc: t.created_at_utc,
      receipt_base64: t.receipt_base64,
      receipt_filename: t.receipt_filename,
    })),
  };

  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/sync`,
      {
        method: "POST",
        headers: {
          ...getCommonHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      },
      12000
    );

    if (isAuthError(res.status)) {
      return { success: false, processedCount: 0, ignoredCount: 0, isUnauthorized: true };
    }

    if (res.status === 422) {
      const errBody = await res.json().catch(() => null);
      let detail = "Error de validación de datos (422)";
      if (errBody?.detail) {
        if (Array.isArray(errBody.detail)) {
          detail = errBody.detail
            .map((d: any) => `${(d.loc || []).join(".")}: ${d.msg || "inválido"}`)
            .join(" | ");
        } else {
          detail = String(errBody.detail);
        }
      }
      console.warn("Validación HTTP 422 en /api/mobile/sync:", detail);
      return {
        success: false,
        processedCount: 0,
        ignoredCount: 0,
        isValidationError: true,
        validationDetail: detail,
      };
    }

    if (!res.ok) {
      console.warn(`Error HTTP ${res.status} en syncTransactionsWithBackend`);
      return null;
    }
    const data = await res.json();
    return {
      success: data.success,
      processedCount: data.processed_count,
      ignoredCount: data.ignored_duplicates_count,
    };
  } catch (err) {
    console.warn("Error de red en syncTransactionsWithBackend:", err);
    return null;
  }
};

export const checkServerStatus = async (): Promise<{ isOnline: boolean; isPaired: boolean }> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/status`,
      { headers: getCommonHeaders() },
      2500
    );

    if (isAuthError(res.status)) {
      return { isOnline: true, isPaired: false };
    }
    if (!res.ok) return { isOnline: false, isPaired: false };

    const data = await res.json();
    const storedToken = getStoredPairingToken();
    const isPaired =
      typeof data.authenticated === "boolean"
        ? data.authenticated
        : !!(storedToken && data.pairing_token && storedToken === data.pairing_token);

    return { isOnline: true, isPaired };
  } catch {
    return { isOnline: false, isPaired: false };
  }
};

export const fetchMonthlySummary = async (month?: string): Promise<MobileMonthlySummary | null> => {
  try {
    const query = month ? `?month=${encodeURIComponent(month)}` : "";
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/summary${query}`,
      { headers: getCommonHeaders() },
      6000
    );
    if (!res.ok) {
      console.warn(`Error HTTP ${res.status} en fetchMonthlySummary`);
      return null;
    }
    return await res.json();
  } catch (err) {
    console.warn("Error de red en fetchMonthlySummary:", err);
    return null;
  }
};

export const updateMonthlyBudget = async (
  subcategoryId: number,
  amount: number,
  month?: string
): Promise<boolean> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/budget`,
      {
        method: "POST",
        headers: {
          ...getCommonHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          subcategory_id: subcategoryId,
          amount,
          month: month || undefined,
        }),
      },
      6000
    );
    return res.ok;
  } catch (err) {
    console.warn("Error de red en updateMonthlyBudget:", err);
    return false;
  }
};

export const createSubcategoryOnTheFly = async (
  name: string,
  categoryName: string
): Promise<SubcategoryItem | null> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/subcategory`,
      {
        method: "POST",
        headers: {
          ...getCommonHeaders(),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ name, category_name: categoryName }),
      },
      6000
    );
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.warn("Error de red en createSubcategoryOnTheFly:", err);
    return null;
  }
};

export const fetchLatestVersion = async (): Promise<MobileVersionInfo | null> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/version`,
      { headers: getCommonHeaders() },
      4000
    );
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.warn("Error de red en fetchLatestVersion:", err);
    return null;
  }
};

export const getApkDownloadUrl = (): string => `${getBaseApiUrl()}/api/mobile/download-apk`;

export const deleteMobileTransaction = async (idOrEventId: string | number): Promise<boolean> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/transactions/${encodeURIComponent(String(idOrEventId))}`,
      {
        method: "DELETE",
        headers: getCommonHeaders(),
      },
      6000
    );
    return res.ok || res.status === 404;
  } catch (err) {
    console.warn("Error de red en deleteMobileTransaction:", err);
    return false;
  }
};

export const searchMobileTransactions = async (
  query: string,
  limit = 50
): Promise<SearchResponse | null> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/transactions/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      { headers: getCommonHeaders() },
      8000
    );
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.warn("Error de red en searchMobileTransactions:", err);
    return null;
  }
};

export const fetchHistoryCache = async (months = 12): Promise<HistoricalTransactionItem[] | null> => {
  try {
    const res = await fetchWithTimeout(
      `${getBaseApiUrl()}/api/mobile/transactions/history-cache?months=${months}`,
      { headers: getCommonHeaders() },
      8000
    );
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    console.warn("Error de red en fetchHistoryCache:", err);
    return null;
  }
};

export const getReceiptImageUrl = (urlOrFilename?: string | null): string | undefined => {
  if (!urlOrFilename) return undefined;
  if (urlOrFilename.startsWith("data:")) return urlOrFilename;
  const path = urlOrFilename.startsWith("/api/") ? urlOrFilename : `/api/mobile/receipts/${urlOrFilename}`;
  let base = `${getBaseApiUrl()}${path}`;
  const token = getStoredPairingToken();
  if (token) {
    base += (base.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(token);
  }
  return base;
};
