/**
 * Fachada de almacenamiento móvil (Spec 016 / Spec 017).
 * Re-exporta los submódulos de storage/*, exporter, offlineEngine y utils/*.
 */
export * from "../utils/categories";
export * from "../utils/formatters";
export * from "./storage/config";
export * from "./storage/transactions";
export * from "./storage/cache";
export * from "./storage/presets";
export * from "./exporter";

import { MobileMonthlySummary, MobileTransaction, SubcategoryItem } from "../types";
import { computeOfflineMonthlySummary } from "./offlineEngine";
import { loadStoredMonthlySummary } from "./storage/cache";

export const getOfflineMonthlySummary = (
  monthStr: string,
  transactions: MobileTransaction[],
  subcategories: SubcategoryItem[]
): MobileMonthlySummary => {
  const lastSummary = loadStoredMonthlySummary();
  return computeOfflineMonthlySummary(
    monthStr,
    transactions,
    subcategories,
    lastSummary?.emergency_fund
  );
};
