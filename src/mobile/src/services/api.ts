import {
  CatalogData,
  HistoricalTransactionItem,
  MobileMonthlySummary,
  MobileTransaction,
  MobileVersionInfo,
  SearchResponse,
  SubcategoryItem,
} from "../types";
import { getStoredPairingToken } from "./storage";

const getBaseApiUrl = (): string => {
  if (typeof window !== "undefined") {
    // Si estamos corriendo en la misma máquina o red (PWA servida desde FastAPI)
    return window.location.origin;
  }
  return "http://localhost:8000";
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
    const isPaired = !!(storedToken && data.pairing_token && storedToken === data.pairing_token);

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


