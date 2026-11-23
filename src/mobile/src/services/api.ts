import {
  CatalogData,
  HistoricalTransactionItem,
  MobileMonthlySummary,
  MobileTransaction,
  MobileVersionInfo,
  SearchResponse,
  SubcategoryItem,
} from "../types";
import { getStoredPairingToken, getStoredServerUrl } from "./storage";

export const getBaseApiUrl = (): string => {
  const customUrl = getStoredServerUrl();
  if (customUrl) return customUrl;

  if (typeof window !== "undefined" && window.location.origin) {
    const orig = window.location.origin;
    if (
      !orig.includes("localhost") &&
      !orig.startsWith("capacitor://") &&
      !orig.startsWith("ionic://") &&
      !orig.startsWith("file://")
    ) {
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

export const testServerConnection = async (
  targetUrl: string,
  token?: string
): Promise<TestConnectionResult> => {
  let cleanUrl = targetUrl.trim().replace(/\/+$/, "");
  if (cleanUrl && !/^https?:\/\//i.test(cleanUrl)) {
    cleanUrl = "http://" + cleanUrl;
  }
  if (!cleanUrl) {
    return { success: false, isPaired: false, message: "La URL del servidor no puede estar vacía" };
  }

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    const headers: Record<string, string> = { Accept: "application/json" };
    const effectiveToken = token !== undefined ? token.trim() : (getStoredPairingToken() || "");
    if (effectiveToken) {
      headers["X-Mobile-Pairing-Token"] = effectiveToken;
    }

    const res = await fetch(`${cleanUrl}/api/mobile/status`, {
      signal: controller.signal,
      headers,
    });
    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      const isPaired = typeof data.authenticated === "boolean" ? data.authenticated : false;
      if (isPaired) {
        return { success: true, isPaired: true, message: "¡Conectado y emparejado con éxito!", statusCode: res.status };
      } else {
        return {
          success: true,
          isPaired: false,
          message: effectiveToken
            ? "Servidor alcanzado, pero el token no coincide"
            : "Servidor alcanzado, pero falta introducir el token",
          statusCode: res.status,
        };
      }
    } else if (res.status === 403) {
      return { success: true, isPaired: false, message: "Acceso denegado: token no coincide con el servidor", statusCode: 403 };
    } else {
      return { success: false, isPaired: false, message: `El servidor respondió con error HTTP ${res.status}`, statusCode: res.status };
    }
  } catch (err: any) {
    if (err.name === "AbortError") {
      return { success: false, isPaired: false, message: "Tiempo de espera agotado (3s). Revisa la IP y la red" };
    }
    return { success: false, isPaired: false, message: "No se pudo conectar al servidor. Comprueba la IP y la red" };
  }
};

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

export const fetchCatalog = async (): Promise<CatalogData | null> => {
  try {
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/catalog`, {
      headers: getCommonHeaders(),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};

export const syncTransactionsWithBackend = async (
  pendingTxs: MobileTransaction[]
): Promise<{ success: boolean; processedCount: number; ignoredCount: number; isUnauthorized?: boolean } | null> => {
  if (pendingTxs.length === 0) {
    return { success: true, processedCount: 0, ignoredCount: 0 };
  }

  const payload = {
    device_id: "mobile-client",
    transactions: pendingTxs.map((t) => ({
      event_id: t.event_id,
      scope: t.scope,
      amount: t.amount,
      description: t.description,
      date: t.date,
      subcategory_id: t.subcategory_id,
      subcategory_name: t.subcategory_name,
      created_at_utc: t.created_at_utc,
    })),
  };

  try {
    const headers = {
      ...getCommonHeaders(),
      "Content-Type": "application/json",
    };
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/sync`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (res.status === 403) {
      return { success: false, processedCount: 0, ignoredCount: 0, isUnauthorized: true };
    }

    if (!res.ok) return null;
    const data = await res.json();
    return {
      success: data.success,
      processedCount: data.processed_count,
      ignoredCount: data.ignored_duplicates_count,
    };
  } catch {
    return null;
  }
};

export const checkServerStatus = async (): Promise<{ isOnline: boolean; isPaired: boolean }> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const res = await fetch(`${getBaseApiUrl()}/api/mobile/status`, {
      signal: controller.signal,
      headers: getCommonHeaders(),
    });
    clearTimeout(timeoutId);

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
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/summary${query}`, {
      headers: getCommonHeaders(),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};

export const updateMonthlyBudget = async (
  subcategoryId: number,
  allocatedAmount: number,
  month?: string
): Promise<boolean> => {
  try {
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/budget`, {
      method: "POST",
      headers: {
        ...getCommonHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        subcategory_id: subcategoryId,
        allocated_amount: allocatedAmount,
        month: month || undefined,
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
};

export const createSubcategoryOnTheFly = async (
  name: string,
  categoryName: string
): Promise<SubcategoryItem | null> => {
  try {
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/subcategory`, {
      method: "POST",
      headers: {
        ...getCommonHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        name,
        category_name: categoryName,
      }),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};

export const fetchLatestVersion = async (): Promise<MobileVersionInfo | null> => {
  try {
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/version`, {
      headers: getCommonHeaders(),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};

export const getApkDownloadUrl = (): string => {
  return `${getBaseApiUrl()}/api/mobile/download-apk`;
};

export const deleteMobileTransaction = async (
  idOrEventId: string | number
): Promise<boolean> => {
  try {
    const res = await fetch(
      `${getBaseApiUrl()}/api/mobile/transactions/${encodeURIComponent(String(idOrEventId))}`,
      {
        method: "DELETE",
        headers: getCommonHeaders(),
      }
    );
    return res.ok;
  } catch {
    return false;
  }
};

export const searchMobileTransactions = async (
  query: string,
  limit = 50
): Promise<SearchResponse | null> => {
  try {
    const res = await fetch(
      `${getBaseApiUrl()}/api/mobile/transactions/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      { headers: getCommonHeaders() }
    );
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};

export const fetchHistoryCache = async (
  months = 12
): Promise<HistoricalTransactionItem[] | null> => {
  try {
    const res = await fetch(
      `${getBaseApiUrl()}/api/mobile/transactions/history-cache?months=${months}`,
      { headers: getCommonHeaders() }
    );
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};


