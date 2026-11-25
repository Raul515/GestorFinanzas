import { EmergencyFundSummary, MobileMonthlySummary, MobileTransaction, SubcategoryItem } from "../types";
import { classifyBudgetBlock, isIncomeSubcategory } from "../utils/categories";
import { getLocalMonthString } from "../utils/formatters";

const round2 = (n: number): number => Math.round(n * 100) / 100;
const calcPct = (spent: number, budget: number): number =>
  budget > 0 ? Math.round((spent / budget) * 1000) / 10 : spent > 0 ? 100 : 0;

/**
 * Motor puro de cálculo offline 50/30/20 (sin acceso directo a localStorage).
 */
export const computeOfflineMonthlySummary = (
  monthStr: string,
  transactions: MobileTransaction[],
  subcategories: SubcategoryItem[],
  emergencyFund?: EmergencyFundSummary
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
    const block = classifyBudgetBlock(sub);
    if (block === "NEEDS") {
      needsSpent += amt;
    } else if (block === "SAVINGS") {
      savingsSpent += amt;
    } else {
      wantsSpent += amt;
    }
    if (t.subcategory_id) {
      subcatSpentMap[t.subcategory_id] = (subcatSpentMap[t.subcategory_id] || 0) + amt;
    }
  });

  const baseIncome = round2(income);
  const needsTarget = round2(baseIncome * 0.5);
  const wantsTarget = round2(baseIncome * 0.3);
  const savingsTarget = round2(baseIncome * 0.2);

  return {
    month: targetMonth,
    total_income: baseIncome,
    total_spent: round2(spent),
    remaining_budget: round2(baseIncome - spent),
    needs: {
      category_name: "Necesidades Básicas (50%)",
      rule_percentage: 50,
      spent: round2(needsSpent),
      budget: needsTarget,
      remaining: round2(needsTarget - needsSpent),
      progress_percentage: calcPct(needsSpent, needsTarget),
    },
    wants: {
      category_name: "Deseos (30%)",
      rule_percentage: 30,
      spent: round2(wantsSpent),
      budget: wantsTarget,
      remaining: round2(wantsTarget - wantsSpent),
      progress_percentage: calcPct(wantsSpent, wantsTarget),
    },
    savings: {
      category_name: "Ahorro e Inversión (20%)",
      rule_percentage: 20,
      spent: round2(savingsSpent),
      budget: savingsTarget,
      remaining: round2(savingsTarget - savingsSpent),
      progress_percentage: calcPct(savingsSpent, savingsTarget),
    },
    emergency_fund: emergencyFund || {
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
        spent: round2(subcatSpentMap[s.id] || 0),
        budget: 0,
      })),
  };
};

/**
 * Superpone transacciones locales aún no sincronizadas (PENDING_SYNC) sobre un resumen base.
 */
export const overlayPendingTransactionsOnSummary = (
  base: MobileMonthlySummary,
  pendingTxs: MobileTransaction[],
  subcategories: SubcategoryItem[]
): MobileMonthlySummary => {
  const monthPending = (pendingTxs || []).filter(
    (t) => t.status === "PENDING_SYNC" && t.date && t.date.startsWith(base.month)
  );
  if (monthPending.length === 0) return base;

  const subcatMap = new Map<number, SubcategoryItem>();
  subcategories.forEach((s) => subcatMap.set(s.id, s));

  let extraIncome = 0;
  let extraSpent = 0;
  let extraNeeds = 0;
  let extraWants = 0;
  let extraSavings = 0;
  const extraSubcat: Record<number, number> = {};

  monthPending.forEach((t) => {
    const amt = Number(t.amount) || 0;
    if (t.type === "INCOME") {
      extraIncome += amt;
      return;
    }
    extraSpent += amt;
    const block = classifyBudgetBlock(subcatMap.get(t.subcategory_id));
    if (block === "NEEDS") extraNeeds += amt;
    else if (block === "SAVINGS") extraSavings += amt;
    else extraWants += amt;

    if (t.subcategory_id) {
      extraSubcat[t.subcategory_id] = (extraSubcat[t.subcategory_id] || 0) + amt;
    }
  });

  const totalIncome = round2(base.total_income + extraIncome);
  const totalSpent = round2(base.total_spent + extraSpent);
  const needsBudget = extraIncome > 0 ? round2(totalIncome * 0.5) : base.needs.budget;
  const wantsBudget = extraIncome > 0 ? round2(totalIncome * 0.3) : base.wants.budget;
  const savingsBudget = extraIncome > 0 ? round2(totalIncome * 0.2) : base.savings.budget;

  const needsSpent = round2(base.needs.spent + extraNeeds);
  const wantsSpent = round2(base.wants.spent + extraWants);
  const savingsSpent = round2(base.savings.spent + extraSavings);

  return {
    ...base,
    total_income: totalIncome,
    total_spent: totalSpent,
    remaining_budget: round2(totalIncome - totalSpent),
    needs: {
      ...base.needs,
      spent: needsSpent,
      budget: needsBudget,
      remaining: round2(needsBudget - needsSpent),
      progress_percentage: calcPct(needsSpent, needsBudget),
    },
    wants: {
      ...base.wants,
      spent: wantsSpent,
      budget: wantsBudget,
      remaining: round2(wantsBudget - wantsSpent),
      progress_percentage: calcPct(wantsSpent, wantsBudget),
    },
    savings: {
      ...base.savings,
      spent: savingsSpent,
      budget: savingsBudget,
      remaining: round2(savingsBudget - savingsSpent),
      progress_percentage: calcPct(savingsSpent, savingsBudget),
    },
    subcategories: base.subcategories.map((s) => ({
      ...s,
      spent: round2(s.spent + (extraSubcat[s.subcategory_id] || 0)),
    })),
  };
};
