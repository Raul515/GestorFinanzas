import { CatalogData, MobileTransaction } from "../types";

const getBaseApiUrl = (): string => {
  if (typeof window !== "undefined") {
    // Si estamos corriendo en la misma máquina o red (PWA servida desde FastAPI)
    return window.location.origin;
  }
  return "http://localhost:8000";
};

export const fetchCatalog = async (): Promise<CatalogData | null> => {
  try {
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/catalog`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
};

export const syncTransactionsWithBackend = async (
  pendingTxs: MobileTransaction[]
): Promise<{ success: boolean; processedCount: number; ignoredCount: number } | null> => {
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
    const res = await fetch(`${getBaseApiUrl()}/api/mobile/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    });

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

export const checkServerStatus = async (): Promise<boolean> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const res = await fetch(`${getBaseApiUrl()}/api/mobile/status`, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return res.ok;
  } catch {
    return false;
  }
};
