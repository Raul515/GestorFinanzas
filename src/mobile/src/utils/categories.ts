import { SubcategoryItem } from "../types";

export type BudgetBlock = "NEEDS" | "WANTS" | "SAVINGS" | "INCOME";

export const isIncomeSubcategory = (
  sub?: Pick<SubcategoryItem, "category_type" | "category_name"> | null
): boolean => {
  if (!sub) return false;
  const cType = (sub.category_type || "").toLowerCase();
  const cName = (sub.category_name || "").toLowerCase();
  return cType === "income" || cType === "ingreso" || cName.includes("ingreso");
};

export const classifyBudgetBlock = (
  sub?: Pick<SubcategoryItem, "category_id" | "category_name" | "category_type"> | null
): BudgetBlock => {
  if (!sub) return "WANTS";
  if (isIncomeSubcategory(sub)) return "INCOME";
  const catLower = (sub.category_name || "").toLowerCase();
  if (catLower.includes("necesidad") || catLower.includes("50") || sub.category_id === 2) {
    return "NEEDS";
  }
  if (catLower.includes("ahorro") || catLower.includes("invers") || catLower.includes("20") || sub.category_id === 4) {
    return "SAVINGS";
  }
  return "WANTS";
};

export const buildTempSubcategory = (
  name: string,
  categoryName: string,
  isIncome = false
): SubcategoryItem => ({
  id: -Math.floor(Date.now() % 1000000),
  name: name.trim(),
  category_id: isIncome ? 1 : categoryName.toLowerCase().includes("necesidad") ? 2 : categoryName.toLowerCase().includes("ahorro") ? 4 : 3,
  category_name: categoryName,
  category_type: isIncome ? "income" : "expense",
  is_frequent: true,
});

export const getSubcategoryEmoji = (name: string): string => {
  const lower = (name || "").toLowerCase();
  if (lower.includes("nómina") || lower.includes("nomina") || lower.includes("salario") || lower.includes("sueldo")) return "💰";
  if (lower.includes("bizum")) return "📲";
  if (lower.includes("devoluc") || lower.includes("reembols")) return "🔄";
  if (lower.includes("venta") || lower.includes("vinted") || lower.includes("wallapop")) return "🏷️";
  if (lower.includes("ingreso") || lower.includes("interes") || lower.includes("dividend")) return "💵";
  if (lower.includes("café") || lower.includes("cafe") || lower.includes("desayun")) return "☕";
  if (lower.includes("super") || lower.includes("compra") || lower.includes("mercadona") || lower.includes("aliment")) return "🛒";
  if (lower.includes("restauran") || lower.includes("cen") || lower.includes("comid") || lower.includes("bar")) return "🍽️";
  if (lower.includes("gasol") || lower.includes("combust") || lower.includes("diesel")) return "⛽";
  if (lower.includes("farmac") || lower.includes("medic") || lower.includes("salud")) return "💊";
  if (lower.includes("transpor") || lower.includes("metro") || lower.includes("bus") || lower.includes("tren")) return "🚇";
  if (lower.includes("pádel") || lower.includes("padel") || lower.includes("gimnas") || lower.includes("deport")) return "🎾";
  if (lower.includes("alquiler") || lower.includes("hipoteca") || lower.includes("hogar") || lower.includes("vivienda")) return "🏠";
  if (lower.includes("luz") || lower.includes("agua") || lower.includes("gas") || lower.includes("suministr")) return "💡";
  if (lower.includes("suscrip") || lower.includes("netflix") || lower.includes("spotify") || lower.includes("internet")) return "📱";
  if (lower.includes("ropa") || lower.includes("calzad")) return "👕";
  if (lower.includes("viaj") || lower.includes("hotel") || lower.includes("vuelo")) return "✈️";
  if (lower.includes("emergenc") || lower.includes("colch")) return "🛡️";
  if (lower.includes("ahorr") || lower.includes("invers")) return "📈";
  return "🏷️";
};
