import { CatalogData, MobileMonthlySummary, MobileTransaction, SubcategoryItem } from "../types";

const STORAGE_KEYS = {
  TRANSACTIONS: "gestor_mobile_transactions",
  CATALOG: "gestor_mobile_catalog",
  SERVER_URL: "gestor_mobile_server_url",
  PAIRING_TOKEN: "gestor_mobile_pairing_token",
  PENDING_DELETES: "gestor_mobile_pending_deletes",
  MONTHLY_SUMMARY: "gestor_mobile_monthly_summary",
};

// Catálogo estándar de fallback si la app se abre por primera vez completamente sin red
export const DEFAULT_FALLBACK_SUBCATEGORIES: SubcategoryItem[] = [
  { id: 1, name: "Café y Desayunos", category_id: 3, category_name: "Deseos (30%)", is_frequent: true },
  { id: 2, name: "Supermercado", category_id: 2, category_name: "Necesidades Básicas (50%)", is_frequent: true },
  { id: 3, name: "Restaurante", category_id: 3, category_name: "Deseos (30%)", is_frequent: true },
  { id: 4, name: "Gasolina", category_id: 2, category_name: "Necesidades Básicas (50%)", is_frequent: true },
  { id: 5, name: "Farmacia", category_id: 2, category_name: "Necesidades Básicas (50%)", is_frequent: true },
  { id: 6, name: "Ocio y Cultura", category_id: 3, category_name: "Deseos (30%)", is_frequent: true },
  { id: 7, name: "Vivienda y Alquiler", category_id: 2, category_name: "Necesidades Básicas (50%)", is_frequent: false },
  { id: 8, name: "Suministros (Luz, Agua)", category_id: 2, category_name: "Necesidades Básicas (50%)", is_frequent: false },
];

export const DEFAULT_FALLBACK_CONCEPTS: string[] = [
  "Café con leche",
  "Desayuno",
  "Mercadona",
  "Menú del día",
  "Gasolina",
  "Cena",
];

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

      // Limpiar el parámetro token de la barra de direcciones sin recargar la página
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

export const loadStoredTransactions = (): MobileTransaction[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.TRANSACTIONS);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
};

export const saveStoredTransactions = (txs: MobileTransaction[]): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(txs));
  } catch (err) {
    console.error("Error guardando transacciones en almacenamiento local:", err);
  }
};

export const deleteStoredTransaction = (eventId: string): MobileTransaction[] => {
  const current = loadStoredTransactions();
  const updated = current.filter((t) => t.event_id !== eventId);
  saveStoredTransactions(updated);
  return updated;
};

export const loadStoredPendingDeletes = (): string[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.PENDING_DELETES);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
};

export const saveStoredPendingDeletes = (ids: string[]): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.PENDING_DELETES, JSON.stringify(ids));
  } catch (err) {
    console.error("Error guardando borrados pendientes:", err);
  }
};

export const addPendingDelete = (idOrEventId: string | number): void => {
  const strId = String(idOrEventId).trim();
  const current = loadStoredPendingDeletes();
  if (!current.includes(strId)) {
    saveStoredPendingDeletes([...current, strId]);
  }
};

export const removePendingDelete = (idOrEventId: string | number): void => {
  const strId = String(idOrEventId).trim();
  const current = loadStoredPendingDeletes();
  saveStoredPendingDeletes(current.filter((id) => id !== strId));
};

export const loadStoredMonthlySummary = (): MobileMonthlySummary | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.MONTHLY_SUMMARY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

export const saveStoredMonthlySummary = (summary: MobileMonthlySummary): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.MONTHLY_SUMMARY, JSON.stringify(summary));
  } catch (err) {
    console.error("Error guardando resumen mensual en almacenamiento local:", err);
  }
};

export const loadStoredCatalog = (): CatalogData => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.CATALOG);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.personal_subcategories && parsed.personal_subcategories.length > 0) {
        return parsed;
      }
    }
  } catch {
    // fallback
  }

  return {
    device_id: "offline-device",
    last_updated_utc: new Date().toISOString(),
    personal_subcategories: DEFAULT_FALLBACK_SUBCATEGORIES,
    frequent_concepts: DEFAULT_FALLBACK_CONCEPTS,
  };
};

export const saveStoredCatalog = (catalog: CatalogData): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.CATALOG, JSON.stringify(catalog));
  } catch (err) {
    console.error("Error guardando catálogo en almacenamiento local:", err);
  }
};

export const addSubcategoryToStoredCatalog = (subcat: SubcategoryItem): CatalogData => {
  const current = loadStoredCatalog();
  const exists = current.personal_subcategories.some(
    (s) => s.name.toLowerCase() === subcat.name.toLowerCase()
  );

  if (!exists) {
    const updated: CatalogData = {
      ...current,
      personal_subcategories: [subcat, ...current.personal_subcategories],
      last_updated_utc: new Date().toISOString(),
    };
    saveStoredCatalog(updated);
    return updated;
  }
  return current;
};

// Exportar transacciones pendientes a un archivo JSON para Syncthing
export const exportTransactionsToJsonFile = (transactions: MobileTransaction[]): void => {
  const pending = transactions.filter((t) => t.status === "PENDING_SYNC");
  const payload = {
    device_id: "mobile-pwa",
    exported_at_utc: new Date().toISOString(),
    transactions: pending.map((t) => ({
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

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `evt_mob_${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
