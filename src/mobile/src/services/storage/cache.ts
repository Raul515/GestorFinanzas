import {
  CatalogData,
  HistoricalTransactionItem,
  MobileMonthlySummary,
  SubcategoryItem,
} from "../../types";
import { STORAGE_KEYS } from "./config";

export const DEFAULT_FALLBACK_SUBCATEGORIES: SubcategoryItem[] = [
  { id: -1, name: "Café y Desayunos", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: true },
  { id: -2, name: "Supermercado", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: true },
  { id: -3, name: "Restaurante", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: true },
  { id: -4, name: "Gasolina", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: true },
  { id: -5, name: "Farmacia", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: true },
  { id: -6, name: "Pádel / Ocio", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: true },
  { id: -7, name: "Alquiler / Hipoteca", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: false },
  { id: -8, name: "Suministros (Luz, Agua)", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: false },
  { id: -9, name: "Suscripciones", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: false },
  { id: -10, name: "Fondo de Emergencia", category_id: 4, category_name: "Ahorro e Inversión (20%)", category_type: "expense", is_frequent: false },
  { id: -11, name: "Salario NETO / Nómina", category_id: 1, category_name: "Ingresos Netos", category_type: "income", is_frequent: true },
  { id: -12, name: "Bizum / Ingreso extra", category_id: 1, category_name: "Ingresos Netos", category_type: "income", is_frequent: true },
  { id: -13, name: "Devoluciones y Reembolsos", category_id: 1, category_name: "Ingresos Netos", category_type: "income", is_frequent: false },
];

export const DEFAULT_FALLBACK_CONCEPTS: string[] = [
  "Café con leche",
  "Desayuno",
  "Mercadona",
  "Menú del día",
  "Gasolina",
  "Cena",
];

export const loadStoredMonthlySummary = (): MobileMonthlySummary | null => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.MONTHLY_SUMMARY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

export const loadStoredMonthlySummariesMap = (): Record<string, MobileMonthlySummary> => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.MONTHLY_SUMMARIES_MAP);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") return parsed;
    }
    const single = loadStoredMonthlySummary();
    if (single && single.month) {
      return { [single.month]: single };
    }
  } catch {
    // fallback
  }
  return {};
};

export const saveStoredMonthlySummariesMap = (map: Record<string, MobileMonthlySummary>): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.MONTHLY_SUMMARIES_MAP, JSON.stringify(map));
  } catch (err) {
    console.error("Error guardando mapa de resúmenes mensuales:", err);
  }
};

export const upsertStoredMonthlySummary = (summary: MobileMonthlySummary): Record<string, MobileMonthlySummary> => {
  const current = loadStoredMonthlySummariesMap();
  const updated = { ...current, [summary.month]: summary };
  saveStoredMonthlySummariesMap(updated);
  return updated;
};

export const saveStoredMonthlySummary = (summary: MobileMonthlySummary): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.MONTHLY_SUMMARY, JSON.stringify(summary));
    if (summary.month) {
      upsertStoredMonthlySummary(summary);
    }
  } catch (err) {
    console.error("Error guardando resumen mensual en almacenamiento local:", err);
  }
};

export const loadStoredHistoryCache = (): HistoricalTransactionItem[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.HISTORY_CACHE);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
};

export const saveStoredHistoryCache = (items: HistoricalTransactionItem[]): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.HISTORY_CACHE, JSON.stringify(items));
  } catch (err) {
    console.error("Error guardando histórico en caché local:", err);
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
