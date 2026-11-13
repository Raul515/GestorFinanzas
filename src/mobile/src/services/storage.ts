import { CatalogData, MobileTransaction, SubcategoryItem } from "../types";

const STORAGE_KEYS = {
  TRANSACTIONS: "gestor_mobile_transactions",
  CATALOG: "gestor_mobile_catalog",
  SERVER_URL: "gestor_mobile_server_url",
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
