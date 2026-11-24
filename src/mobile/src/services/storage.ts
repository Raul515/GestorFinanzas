import { Capacitor } from "@capacitor/core";
import { Filesystem, Directory, Encoding } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";
import {
  CatalogData,
  HistoricalTransactionItem,
  MobileMonthlySummary,
  MobileTransaction,
  QuickPresetItem,
  SubcategoryItem,
} from "../types";

const STORAGE_KEYS = {
  TRANSACTIONS: "gestor_mobile_transactions",
  CATALOG: "gestor_mobile_catalog",
  SERVER_URL: "gestor_mobile_server_url",
  PAIRING_TOKEN: "gestor_mobile_pairing_token",
  PENDING_DELETES: "gestor_mobile_pending_deletes",
  MONTHLY_SUMMARY: "gestor_mobile_monthly_summary",
  MONTHLY_SUMMARIES_MAP: "gestor_mobile_monthly_summaries_map",
  HISTORY_CACHE: "gestor_mobile_history_cache",
  QUICK_PRESETS: "gestor_mobile_quick_presets",
};

export const getLocalDateString = (d: Date = new Date()): string => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export const getLocalMonthString = (d: Date = new Date()): string => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
};

export const isIncomeSubcategory = (
  sub?: Pick<SubcategoryItem, "category_type" | "category_name"> | null
): boolean => {
  if (!sub) return false;
  const cType = (sub.category_type || "").toLowerCase();
  const cName = (sub.category_name || "").toLowerCase();
  return cType === "income" || cType === "ingreso" || cName.includes("ingreso");
};

// Catálogo estándar de fallback si la app se abre por primera vez completamente sin red
export const DEFAULT_FALLBACK_SUBCATEGORIES: SubcategoryItem[] = [
  { id: 1, name: "Café y Desayunos", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: true },
  { id: 2, name: "Supermercado", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: true },
  { id: 3, name: "Restaurante", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: true },
  { id: 4, name: "Gasolina", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: true },
  { id: 5, name: "Farmacia", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: true },
  { id: 6, name: "Pádel / Ocio", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: true },
  { id: 7, name: "Alquiler / Hipoteca", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: false },
  { id: 8, name: "Suministros (Luz, Agua)", category_id: 2, category_name: "Necesidades Básicas (50%)", category_type: "expense", is_frequent: false },
  { id: 9, name: "Suscripciones", category_id: 3, category_name: "Deseos (30%)", category_type: "expense", is_frequent: false },
  { id: 10, name: "Fondo de Emergencia", category_id: 4, category_name: "Ahorro e Inversión (20%)", category_type: "expense", is_frequent: false },
  { id: 11, name: "Salario NETO / Nómina", category_id: 1, category_name: "Ingresos Netos", category_type: "income", is_frequent: true },
  { id: 12, name: "Bizum / Ingreso extra", category_id: 1, category_name: "Ingresos Netos", category_type: "income", is_frequent: true },
  { id: 13, name: "Devoluciones y Reembolsos", category_id: 1, category_name: "Ingresos Netos", category_type: "income", is_frequent: false },
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

export const getStoredServerUrl = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEYS.SERVER_URL);
  } catch {
    return null;
  }
};

export const saveStoredServerUrl = (rawUrl: string): string => {
  try {
    let clean = (rawUrl || "").trim().replace(/\/+$/, "");
    if (clean && !/^https?:\/\//i.test(clean)) {
      clean = "http://" + clean;
    }
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

    // Si no había una URL configurada manualmente por el usuario y estamos en un navegador cargando
    // la app desde una IP de red real (no localhost ni app empaquetada), inicializar con el origen activo
    const existingStored = getStoredServerUrl();
    if (existingStored && existingStored.trim()) {
      return existingStored.trim();
    }

    if (window.location.origin) {
      const orig = window.location.origin;
      if (
        !orig.includes("localhost") &&
        !orig.includes("127.0.0.1") &&
        !orig.startsWith("capacitor://") &&
        !orig.startsWith("ionic://") &&
        !orig.startsWith("file://")
      ) {
        return saveStoredServerUrl(orig);
      }
    }
  } catch (err) {
    console.warn("No se pudo inspeccionar el servidor en la URL:", err);
  }

  return getStoredServerUrl();
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
    console.warn("Cuota de almacenamiento excedida, intentando purgar imágenes sincronizadas:", err);
    try {
      let cleaned = false;
      const stripped = txs.map((t) => {
        if (t.status === "SYNCED" && t.receipt_base64) {
          cleaned = true;
          return { ...t, receipt_base64: undefined };
        }
        return t;
      });
      if (cleaned) {
        localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(stripped));
        return;
      }
      const fullyStripped = txs.map((t) => ({ ...t, receipt_base64: undefined }));
      localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(fullyStripped));
    } catch (retryErr) {
      console.error("Fallo crítico al guardar en localStorage tras purgar comprobantes:", retryErr);
    }
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
    if (summary.month) {
      upsertStoredMonthlySummary(summary);
    }
  } catch (err) {
    console.error("Error guardando resumen mensual en almacenamiento local:", err);
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

export const getOfflineMonthlySummary = (
  monthStr: string,
  transactions: MobileTransaction[],
  subcategories: SubcategoryItem[]
): MobileMonthlySummary => {
  const targetMonth = monthStr || getLocalMonthString();
  const subcatMap = new Map<number, SubcategoryItem>();
  subcategories.forEach((s) => subcatMap.set(s.id, s));

  const monthTxs = (transactions || []).filter((t) => t.date && t.date.startsWith(targetMonth));
  let spent = 0;
  let income = 0;
  let needsSpent = 0;
  let wantsSpent = 0;
  let savingsSpent = 0;
  const subcatSpentMap: Record<number, number> = {};

  monthTxs.forEach((t) => {
    const amt = Number(t.amount) || 0;
    if (t.type === "INCOME") {
      income += amt;
      return;
    }
    spent += amt;
    const sub = subcatMap.get(t.subcategory_id);
    const catLower = (sub?.category_name || "").toLowerCase();
    if (catLower.includes("necesidad") || catLower.includes("50") || sub?.category_id === 2) {
      needsSpent += amt;
    } else if (catLower.includes("ahorro") || catLower.includes("20") || sub?.category_id === 4) {
      savingsSpent += amt;
    } else {
      wantsSpent += amt;
    }
    if (t.subcategory_id) {
      subcatSpentMap[t.subcategory_id] = (subcatSpentMap[t.subcategory_id] || 0) + amt;
    }
  });

  const baseIncome = Math.round(income * 100) / 100;
  const needsTarget = Math.round(baseIncome * 0.5 * 100) / 100;
  const wantsTarget = Math.round(baseIncome * 0.3 * 100) / 100;
  const savingsTarget = Math.round(baseIncome * 0.2 * 100) / 100;
  const lastSummary = loadStoredMonthlySummary();

  return {
    month: targetMonth,
    total_income: baseIncome,
    total_spent: Math.round(spent * 100) / 100,
    remaining_budget: Math.round((baseIncome - spent) * 100) / 100,
    needs: {
      category_name: "Necesidades Básicas (50%)",
      rule_percentage: 50,
      spent: Math.round(needsSpent * 100) / 100,
      budget: needsTarget,
      remaining: Math.round((needsTarget - needsSpent) * 100) / 100,
      progress_percentage: needsTarget > 0 ? Math.round((needsSpent / needsTarget) * 1000) / 10 : needsSpent > 0 ? 100 : 0,
    },
    wants: {
      category_name: "Deseos (30%)",
      rule_percentage: 30,
      spent: Math.round(wantsSpent * 100) / 100,
      budget: wantsTarget,
      remaining: Math.round((wantsTarget - wantsSpent) * 100) / 100,
      progress_percentage: wantsTarget > 0 ? Math.round((wantsSpent / wantsTarget) * 1000) / 10 : wantsSpent > 0 ? 100 : 0,
    },
    savings: {
      category_name: "Ahorro e Inversión (20%)",
      rule_percentage: 20,
      spent: Math.round(savingsSpent * 100) / 100,
      budget: savingsTarget,
      remaining: Math.round((savingsTarget - savingsSpent) * 100) / 100,
      progress_percentage: savingsTarget > 0 ? Math.round((savingsSpent / savingsTarget) * 1000) / 10 : savingsSpent > 0 ? 100 : 0,
    },
    emergency_fund: lastSummary?.emergency_fund || {
      current_amount: 0,
      target_amount: 0,
      months_covered: 0,
      is_funded: false,
    },
    subcategories: subcategories
      .filter((s) => !isIncomeSubcategory(s))
      .map((s) => ({
        subcategory_id: s.id,
        subcategory_name: s.name,
        category_name: s.category_name,
        spent: Math.round((subcatSpentMap[s.id] || 0) * 100) / 100,
        budget: 0,
      })),
  };
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

// Exportar transacciones pendientes a un archivo JSON para Syncthing
export const isIOSDevice = (): boolean => {
  if (typeof navigator === "undefined") return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent || "") ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
};

export const exportTransactionsToJsonFile = async (transactions: MobileTransaction[]): Promise<void> => {
  const pending = transactions.filter((t) => t.status === "PENDING_SYNC");
  const payload = {
    device_id: Capacitor.isNativePlatform() ? "mobile-apk" : "mobile-pwa",
    exported_at_utc: new Date().toISOString(),
    transactions: pending.map((t) => ({
      event_id: t.event_id,
      scope: t.scope,
      type: t.type || "EXPENSE",
      amount: t.amount,
      description: t.description,
      date: t.date,
      subcategory_id: t.subcategory_id,
      subcategory_name: t.subcategory_name,
      created_at_utc: t.created_at_utc,
    })),
  };

  const jsonStr = JSON.stringify(payload, null, 2);
  const filename = `evt_mob_${Date.now()}.json`;

  if (Capacitor.isNativePlatform()) {
    try {
      const savedFile = await Filesystem.writeFile({
        path: filename,
        data: jsonStr,
        directory: Directory.Cache,
        encoding: Encoding.UTF8,
      });
      await Share.share({
        title: "Exportación Gestor Finanzas",
        text: `Lote de ${pending.length} movimientos pendientes exportados.`,
        url: savedFile.uri,
        files: [savedFile.uri],
        dialogTitle: "Guardar o compartir JSON",
      });
      return;
    } catch (nativeErr: any) {
      if (nativeErr?.message && String(nativeErr.message).toLowerCase().includes("cancel")) {
        return;
      }
      console.warn("Fallo en exportación nativa Capacitor, usando fallback web:", nativeErr);
    }
  }

  if (typeof navigator !== "undefined" && navigator.share && navigator.canShare) {
    try {
      const file = new File([jsonStr], filename, { type: "application/json" });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({
          files: [file],
          title: "Exportación Gestor Finanzas",
          text: `Lote de ${pending.length} gastos pendientes exportados.`,
        });
        return;
      }
    } catch (err: any) {
      if (err && err.name === "AbortError") {
        return;
      }
      console.warn("Fallo al compartir archivo con navigator.share, usando fallback de descarga:", err);
    }
  }

  const blob = new Blob([jsonStr], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

// Atajos Rápidos por defecto (Spec 016 - Fase 14 / RF-18)
export const DEFAULT_QUICK_PRESETS: QuickPresetItem[] = [
  {
    id: "preset-cafe",
    name: "Café",
    emoji: "☕",
    amount: 1.5,
    subcategory_name: "Salir a comer fuera",
    concept: "Café",
  },
  {
    id: "preset-cena",
    name: "Cena",
    emoji: "🍽️",
    amount: 20.0,
    subcategory_name: "Salir a comer fuera",
    concept: "Cena",
  },
  {
    id: "preset-cine",
    name: "Cine",
    emoji: "🎬",
    amount: 5.5,
    subcategory_name: "Entretenimiento (Tomar algo...)",
    concept: "Cine",
  },
];

export const loadStoredQuickPresets = (): QuickPresetItem[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.QUICK_PRESETS);
    if (!raw) return DEFAULT_QUICK_PRESETS;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed;
    }
    return DEFAULT_QUICK_PRESETS;
  } catch {
    return DEFAULT_QUICK_PRESETS;
  }
};

export const saveStoredQuickPresets = (presets: QuickPresetItem[]): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.QUICK_PRESETS, JSON.stringify(presets));
  } catch (err) {
    console.error("Error guardando atajos rápidos en almacenamiento local:", err);
  }
};

export const resetStoredQuickPresets = (): QuickPresetItem[] => {
  saveStoredQuickPresets(DEFAULT_QUICK_PRESETS);
  return DEFAULT_QUICK_PRESETS;
};

export const findMatchingSubcategory = (
  preset: Pick<QuickPresetItem, "subcategory_id" | "subcategory_name" | "name"> | string,
  subcats: SubcategoryItem[]
): SubcategoryItem | null => {
  if (!subcats || subcats.length === 0) return null;
  const targetId = typeof preset === "object" ? preset.subcategory_id : undefined;
  const rawName = typeof preset === "object" ? preset.subcategory_name || preset.name || "" : String(preset || "");
  const targetName = rawName.toLowerCase().trim();

  if (targetId) {
    const byId = subcats.find((s) => s.id === targetId);
    if (byId) return byId;
  }
  if (!targetName) return null;

  let found = subcats.find((s) => s.name.toLowerCase() === targetName);
  if (found) return found;

  found = subcats.find((s) => s.name.toLowerCase().includes(targetName) || targetName.includes(s.name.toLowerCase()));
  if (found) return found;

  const isCoffee = targetName.includes("café") || targetName.includes("cafe") || targetName.includes("desayuno");
  const isDining = targetName.includes("cena") || targetName.includes("comida") || targetName.includes("restaurante") || targetName.includes("comer") || targetName.includes("almuerzo");
  const isLeisure = targetName.includes("cine") || targetName.includes("ocio") || targetName.includes("cultura") || targetName.includes("copa") || targetName.includes("tomar");
  const isGrocery = targetName.includes("super") || targetName.includes("compra") || targetName.includes("aliment") || targetName.includes("mercado");
  const isGym = targetName.includes("gym") || targetName.includes("gimnasio") || targetName.includes("deporte");
  const isFuel = targetName.includes("gasolina") || targetName.includes("diesel") || targetName.includes("transporte") || targetName.includes("metro");

  if (isCoffee) {
    return (
      subcats.find((s) => {
        const sn = s.name.toLowerCase();
        return sn.includes("café") || sn.includes("cafe") || sn.includes("desayuno");
      }) ||
      subcats.find((s) => s.name.toLowerCase().includes("salir a comer") || s.name.toLowerCase().includes("restaurante")) ||
      subcats.find((s) => s.name.toLowerCase().includes("tomar algo") || s.name.toLowerCase().includes("entretenimiento")) ||
      null
    );
  }
  if (isDining) {
    return (
      subcats.find((s) => {
        const sn = s.name.toLowerCase();
        return sn.includes("restaurante") || sn.includes("cena") || sn.includes("comida") || sn.includes("almuerzo");
      }) ||
      subcats.find((s) => s.name.toLowerCase().includes("salir a comer")) ||
      subcats.find((s) => s.name.toLowerCase().includes("alimentación")) ||
      null
    );
  }
  if (isLeisure) {
    return (
      subcats.find((s) => {
        const sn = s.name.toLowerCase();
        return sn.includes("entretenimiento") || sn.includes("ocio") || sn.includes("hobbies") || sn.includes("cine");
      }) || null
    );
  }
  if (isGrocery) {
    return (
      subcats.find((s) => {
        const sn = s.name.toLowerCase();
        return sn.includes("alimentación") || sn.includes("supermercado") || sn.includes("compra");
      }) || null
    );
  }
  if (isGym) {
    return (
      subcats.find((s) => {
        const sn = s.name.toLowerCase();
        return sn.includes("gimnasio") || sn.includes("gym") || sn.includes("deporte");
      }) || null
    );
  }
  if (isFuel) {
    return (
      subcats.find((s) => {
        const sn = s.name.toLowerCase();
        return sn.includes("gasolina") || sn.includes("transporte") || sn.includes("combustible");
      }) || null
    );
  }
  return null;
};

