import { useState, useEffect, useCallback, ChangeEvent } from "react";
import { RefreshCw, ShieldCheck, AlertTriangle, Edit3, Check, X, TrendingUp, PieChart } from "lucide-react";
import { MobileMonthlySummary, MobileSubcategorySummary } from "../types";
import { fetchMonthlySummary, updateMonthlyBudget } from "../services/api";
import { getSubcategoryEmoji } from "./CategoryChips";

interface MonthlySummaryViewProps {
  isServerOnline: boolean;
}

export const MonthlySummaryView = ({ isServerOnline }: MonthlySummaryViewProps) => {
  const [currentMonth, setCurrentMonth] = useState(() => {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    return `${y}-${m}`;
  });

  const [summary, setSummary] = useState<MobileMonthlySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingSubcatId, setEditingSubcatId] = useState<number | null>(null);
  const [editAmountStr, setEditAmountStr] = useState("");
  const [savingBudget, setSavingBudget] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadData = useCallback(async (monthStr: string) => {
    if (!isServerOnline) {
      setErrorMessage("Modo offline: Conéctate a tu red local para consultar y actualizar el resumen.");
      return;
    }
    setLoading(true);
    setErrorMessage(null);
    try {
      const data = await fetchMonthlySummary(monthStr);
      if (data) {
        setSummary(data);
      } else {
        setErrorMessage("No se pudo cargar el resumen mensual. Verifica la conexión con tu PC.");
      }
    } catch {
      setErrorMessage("Error de conexión al cargar el resumen.");
    } finally {
      setLoading(false);
    }
  }, [isServerOnline]);

  useEffect(() => {
    if (isServerOnline) {
      loadData(currentMonth);
    }
  }, [currentMonth, isServerOnline, loadData]);

  const handleStartEdit = (subcat: MobileSubcategorySummary) => {
    setEditingSubcatId(subcat.subcategory_id);
    setEditAmountStr(String(subcat.budget || 0));
  };

  const handleSaveBudget = async (subcategoryId: number) => {
    const num = parseFloat(editAmountStr.replace(",", ".")) || 0;
    setSavingBudget(true);
    try {
      const ok = await updateMonthlyBudget(subcategoryId, num, currentMonth);
      if (ok) {
        setEditingSubcatId(null);
        await loadData(currentMonth);
      } else {
        alert("No se pudo actualizar el presupuesto. Comprueba la conexión.");
      }
    } finally {
      setSavingBudget(false);
    }
  };

  const formatEuro = (val: number) => {
    return (val || 0).toLocaleString("es-ES", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + " €";
  };

  const MONTH_NAMES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
  ];

  const formatMonthLabelEs = (monthStr: string) => {
    const parts = (monthStr || "").split("-");
    if (parts.length !== 2) return monthStr;
    const idx = parseInt(parts[1], 10) - 1;
    return `${MONTH_NAMES_ES[idx] || parts[1]} ${parts[0]}`;
  };

  const getMonthOptions = (activeMonth: string) => {
    const now = new Date();
    const opts: string[] = [];
    const seen = new Set<string>();
    for (let offset = 3; offset >= -24; offset--) {
      const d = new Date(now.getFullYear(), now.getMonth() + offset, 1);
      const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      if (!seen.has(val)) {
        seen.add(val);
        opts.push(val);
      }
    }
    if (activeMonth && !seen.has(activeMonth)) {
      opts.push(activeMonth);
      opts.sort((a, b) => b.localeCompare(a));
    }
    return opts;
  };

  const shiftMonth = (delta: number) => {
    const [y, m] = currentMonth.split("-").map(Number);
    if (Number.isNaN(y) || Number.isNaN(m)) return;
    const d = new Date(y, m - 1 + delta, 1);
    setCurrentMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };

  return (
    <div className="flex-1 flex flex-col max-w-sm mx-auto w-full px-3 py-2 overflow-y-auto no-scrollbar gap-2.5 text-slate-100">
      {/* Cabecera con selector de mes universal (compatible iOS/Android) y botón de refresco */}
      <div className="flex items-center justify-between pt-0.5 gap-2">
        <div className="flex items-center gap-2 shrink-0">
          <div className="p-1.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <PieChart className="w-4 h-4" />
          </div>
          <div>
            <h2 className="font-black text-sm tracking-tight text-slate-100">Mi Mes</h2>
            <p className="text-[10px] text-slate-400 font-medium">Ejecución y presupuestos</p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => shiftMonth(-1)}
            className="px-2 py-1 rounded-lg bg-[#0F172A] border border-white/[0.08] text-slate-300 text-xs font-bold active:scale-95"
            title="Mes anterior"
          >
            ◀
          </button>
          <select
            value={currentMonth}
            onChange={(e: ChangeEvent<HTMLSelectElement>) => setCurrentMonth(e.target.value)}
            className="bg-[#0F172A] border border-white/[0.08] text-xs font-bold rounded-xl px-2 py-1 text-slate-200 focus:outline-none focus:border-emerald-500/60"
          >
            {getMonthOptions(currentMonth).map((mVal) => (
              <option key={mVal} value={mVal}>
                {formatMonthLabelEs(mVal)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            className="px-2 py-1 rounded-lg bg-[#0F172A] border border-white/[0.08] text-slate-300 text-xs font-bold active:scale-95"
            title="Mes siguiente"
          >
            ▶
          </button>
          <button
            type="button"
            onClick={() => loadData(currentMonth)}
            disabled={loading || !isServerOnline}
            className="p-1.5 rounded-xl bg-[#0F172A] border border-white/[0.08] text-slate-400 hover:text-emerald-400 active:scale-95 disabled:opacity-50 transition-all shadow-sm"
            title={isServerOnline ? "Recargar métricas" : "Servidor desconectado"}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-emerald-400" : ""}`} />
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-2xl text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          <span className="leading-tight">{errorMessage}</span>
        </div>
      )}

      {loading && !summary && (
        <div className="py-14 flex flex-col items-center justify-center gap-2 text-slate-500 text-xs">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />
          <span className="font-medium">Calculando métricas del mes...</span>
        </div>
      )}

      {summary && (
        <>
          {/* Tarjetas Gemelas de Balance Financiero */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-[#0F172A] border border-white/[0.08] rounded-2xl p-3 flex flex-col justify-between shadow-sm">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Gastado Total</span>
              <span className="text-xl font-black text-rose-400 mt-1 font-mono tracking-tight">
                {formatEuro(summary.total_spent)}
              </span>
              <span className="text-[10px] text-slate-500 font-medium mt-1 truncate">
                Ingresos: {formatEuro(summary.total_income)}
              </span>
            </div>

            <div className="bg-[#0F172A] border border-white/[0.08] rounded-2xl p-3 flex flex-col justify-between shadow-sm">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Disponible</span>
              <span
                className={`text-xl font-black mt-1 font-mono tracking-tight ${
                  summary.remaining_budget >= 0 ? "text-emerald-400" : "text-amber-400"
                }`}
              >
                {formatEuro(summary.remaining_budget)}
              </span>
              <span className="text-[10px] text-slate-500 font-medium mt-1">
                {summary.remaining_budget >= 0 ? "✓ Margen positivo" : "⚠️ Presupuesto excedido"}
              </span>
            </div>
          </div>

          {/* Bloque Regla 50/30/20 */}
          <div className="bg-[#0F172A] border border-white/[0.08] rounded-2xl p-3.5 flex flex-col gap-3 shadow-sm">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-black text-slate-200">Presupuesto 50 / 30 / 20</span>
              </div>
              <span className="text-[10px] font-semibold text-emerald-400/90 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                Objetivo Saludable
              </span>
            </div>

            {/* Necesidades 50% */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">🛒</span>
                  <span className="font-bold text-slate-200 text-[11.5px]">Necesidades (50%)</span>
                </div>
                <span className="text-slate-300 font-mono text-[11px] font-semibold">
                  {formatEuro(summary.needs.spent)} <span className="text-slate-600 font-normal">/</span> {formatEuro(summary.needs.budget)}
                </span>
              </div>
              <div className="w-full bg-[#070B12] h-2 rounded-full overflow-hidden border border-white/[0.06]">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    summary.needs.progress_percentage > 100
                      ? "bg-rose-500"
                      : "bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.4)]"
                  }`}
                  style={{ width: `${Math.min(summary.needs.progress_percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 font-medium">
                <span>{summary.needs.progress_percentage.toFixed(0)}% consumido</span>
                <span>Restante: {formatEuro(summary.needs.remaining)}</span>
              </div>
            </div>

            {/* Deseos 30% */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">☕</span>
                  <span className="font-bold text-slate-200 text-[11.5px]">Deseos (30%)</span>
                </div>
                <span className="text-slate-300 font-mono text-[11px] font-semibold">
                  {formatEuro(summary.wants.spent)} <span className="text-slate-600 font-normal">/</span> {formatEuro(summary.wants.budget)}
                </span>
              </div>
              <div className="w-full bg-[#070B12] h-2 rounded-full overflow-hidden border border-white/[0.06]">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    summary.wants.progress_percentage >= 100
                      ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.4)]"
                      : summary.wants.progress_percentage >= 80
                      ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.4)]"
                      : "bg-violet-400 shadow-[0_0_8px_rgba(167,139,250,0.4)]"
                  }`}
                  style={{ width: `${Math.min(summary.wants.progress_percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 font-medium">
                <span>{summary.wants.progress_percentage.toFixed(0)}% consumido</span>
                <span>Restante: {formatEuro(summary.wants.remaining)}</span>
              </div>
            </div>

            {/* Ahorro 20% */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm">📈</span>
                  <span className="font-bold text-slate-200 text-[11.5px]">Ahorro e Inversión (20%)</span>
                </div>
                <span className="text-slate-300 font-mono text-[11px] font-semibold">
                  {formatEuro(summary.savings.spent)} <span className="text-slate-600 font-normal">/</span> {formatEuro(summary.savings.budget)}
                </span>
              </div>
              <div className="w-full bg-[#070B12] h-2 rounded-full overflow-hidden border border-white/[0.06]">
                <div
                  className="h-full bg-emerald-400 rounded-full transition-all duration-500 shadow-[0_0_8px_rgba(52,211,153,0.4)]"
                  style={{ width: `${Math.min(summary.savings.progress_percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-400 font-medium">
                <span>{summary.savings.progress_percentage.toFixed(0)}% alcanzado</span>
                <span>Meta mensual: {formatEuro(summary.savings.budget)}</span>
              </div>
            </div>
          </div>

          {/* Tarjeta Acorazada del Fondo de Emergencia (Salvaguarda Constitucional) */}
          <div className="bg-[#0F172A] border border-white/[0.08] rounded-2xl p-3.5 flex flex-col gap-2.5 shadow-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`p-1.5 rounded-xl border ${
                  summary.emergency_fund.is_funded
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                }`}>
                  <ShieldCheck className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-black text-slate-100">Fondo de Seguridad</div>
                  <div className="text-[10px] text-slate-400 font-medium">Reserva patrimonial blindada</div>
                </div>
              </div>

              <span
                className={`text-[10.5px] font-extrabold px-2.5 py-0.5 rounded-full border ${
                  summary.emergency_fund.is_funded
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                    : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                }`}
              >
                {summary.emergency_fund.months_covered.toFixed(1)} meses
              </span>
            </div>

            <div className="flex items-baseline justify-between pt-1">
              <span className="text-base font-black text-slate-100 font-mono tracking-tight">
                {formatEuro(summary.emergency_fund.current_amount)}
              </span>
              <span className="text-[11px] text-slate-400 font-medium">
                Meta (3 meses): {formatEuro(summary.emergency_fund.target_amount)}
              </span>
            </div>

            {/* Barra de progreso de la reserva */}
            <div className="w-full bg-[#070B12] h-1.5 rounded-full overflow-hidden border border-white/[0.06]">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  summary.emergency_fund.is_funded
                    ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.4)]"
                    : "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.4)]"
                }`}
                style={{
                  width: `${Math.min(
                    summary.emergency_fund.target_amount > 0
                      ? (summary.emergency_fund.current_amount / summary.emergency_fund.target_amount) * 100
                      : 0,
                    100
                  )}%`,
                }}
              />
            </div>
          </div>

          {/* Ajuste de Presupuesto por Subcategoría */}
          <div className="bg-[#0F172A] border border-white/[0.08] rounded-2xl p-3.5 flex flex-col gap-2 shadow-sm mb-2">
            <div className="flex items-center justify-between pb-1.5 border-b border-white/[0.06]">
              <div className="flex items-center gap-1.5">
                <PieChart className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-black text-slate-200">Presupuestos por Categoría</span>
              </div>
              <span className="text-[10px] text-slate-400 font-medium">Toca ✏️ para editar</span>
            </div>

            <div className="flex flex-col gap-1.5 divide-y divide-white/[0.04]">
              {summary.subcategories.map((subcat) => {
                const isEditing = editingSubcatId === subcat.subcategory_id;
                const emoji = getSubcategoryEmoji(subcat.subcategory_name);
                const progressPct = subcat.budget > 0 ? (subcat.spent / subcat.budget) * 100 : 0;

                return (
                  <div
                    key={subcat.subcategory_id}
                    className="pt-2 flex flex-col gap-1"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm shrink-0">{emoji}</span>
                        <div className="min-w-0">
                          <span className="font-bold text-slate-200 text-xs truncate block">{subcat.subcategory_name}</span>
                          <span className="text-[10px] text-slate-400 font-medium">
                            Gastado: {formatEuro(subcat.spent)}
                          </span>
                        </div>
                      </div>

                      {isEditing ? (
                        <div className="flex items-center gap-1.5 shrink-0">
                          <input
                            type="number"
                            step="1"
                            value={editAmountStr}
                            onChange={(e: ChangeEvent<HTMLInputElement>) => setEditAmountStr(e.target.value)}
                            className="w-18 bg-[#070B12] border border-emerald-500 rounded-lg px-2 py-1 text-xs text-slate-100 font-mono text-right focus:outline-none"
                            autoFocus
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveBudget(subcat.subcategory_id)}
                            disabled={savingBudget}
                            className="p-1 rounded-lg bg-emerald-500 text-slate-950 font-bold active:scale-95 shadow-sm"
                            title="Guardar"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingSubcatId(null)}
                            className="p-1 rounded-lg bg-slate-800 text-slate-400 active:scale-95"
                            title="Cancelar"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="font-mono text-slate-200 font-bold text-xs">
                            {formatEuro(subcat.budget)}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleStartEdit(subcat)}
                            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-emerald-400 active:scale-95 transition-all"
                            title="Modificar presupuesto"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Micro barra de avance por subcategoría */}
                    {subcat.budget > 0 && (
                      <div className="w-full bg-[#070B12] h-1 rounded-full overflow-hidden border border-white/[0.04]">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            progressPct >= 100
                              ? "bg-rose-500"
                              : progressPct >= 80
                              ? "bg-amber-400"
                              : "bg-emerald-400/80"
                          }`}
                          style={{ width: `${Math.min(progressPct, 100)}%` }}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
};
