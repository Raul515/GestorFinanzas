import { QuickPresetItem, SubcategoryItem } from "../../types";
import { STORAGE_KEYS } from "./config";

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

const KEYWORD_MATCHERS: Array<{ triggers: string[]; groups: string[][] }> = [
  {
    triggers: ["café", "cafe", "desayuno"],
    groups: [["café", "cafe", "desayuno"], ["salir a comer", "restaurante"], ["tomar algo", "entretenimiento"]],
  },
  {
    triggers: ["cena", "comida", "restaurante", "comer", "almuerzo"],
    groups: [["restaurante", "cena", "comida", "almuerzo"], ["salir a comer"], ["alimentación"]],
  },
  {
    triggers: ["cine", "ocio", "cultura", "copa", "tomar"],
    groups: [["entretenimiento", "ocio", "hobbies", "cine"]],
  },
  {
    triggers: ["super", "compra", "aliment", "mercado"],
    groups: [["alimentación", "supermercado", "compra"]],
  },
  {
    triggers: ["gym", "gimnasio", "deporte"],
    groups: [["gimnasio", "gym", "deporte"]],
  },
  {
    triggers: ["gasolina", "diesel", "transporte", "metro"],
    groups: [["gasolina", "transporte", "combustible"]],
  },
];

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

  const exact = subcats.find((s) => s.name.toLowerCase() === targetName);
  if (exact) return exact;

  const partial = subcats.find(
    (s) => s.name.toLowerCase().includes(targetName) || targetName.includes(s.name.toLowerCase())
  );
  if (partial) return partial;

  for (const matcher of KEYWORD_MATCHERS) {
    if (matcher.triggers.some((t) => targetName.includes(t))) {
      for (const kwGroup of matcher.groups) {
        const hit = subcats.find((s) => {
          const sn = s.name.toLowerCase();
          return kwGroup.some((kw) => sn.includes(kw));
        });
        if (hit) return hit;
      }
      return null;
    }
  }
  return null;
};
