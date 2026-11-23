import { useState, useEffect, useCallback, ChangeEvent } from "react";
import { RefreshCw, ShieldCheck, AlertTriangle, Edit3, Check, X, TrendingUp, PieChart } from "lucide-react";
import { MobileMonthlySummary, MobileSubcategorySummary } from "../types";
import { fetchMonthlySummary, updateMonthlyBudget } from "../services/api";

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

  return (
    <div className="flex-1 flex flex-col max-w-sm mx-auto w-full px-3 py-2 overflow-y-auto no-scrollbar gap-3 text-slate-100">
      {/* Cabecera con selector de mes y botón de refresco */}
      <div className="flex items-center justify-between pt-1">
        <div className="flex items-center gap-2">
          <PieChart className="w-5 h-5 text-emerald-400" />
          <h2 className="font-extrabold text-base text-slate-100">Mi Mes</h2>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="month"
            value={currentMonth}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setCurrentMonth(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-xs font-semibold rounded-xl px-2.5 py-1 text-slate-200 focus:outline-none focus:border-emerald-500"
          />
          <button
            type="button"
            onClick={() => loadData(currentMonth)}
            disabled={loading || !isServerOnline}
            className="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-emerald-400 active:scale-95 disabled:opacity-50"
            title={isServerOnline ? "Recargar" : "Servidor desconectado"}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-emerald-400" : ""}`} />
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-300 rounded-xl text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {loading && !summary && (
        <div className="py-12 flex flex-col items-center justify-center gap-2 text-slate-500 text-sm">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />
          <span>Calculando métricas del mes...</span>
        </div>
      )}

      {summary && (
        <>
          {/* Tarjeta de Resumen Global */}
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-slate-900/90 border border-slate-800/80 rounded-2xl p-3 flex flex-col justify-between">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Gastado</span>
              <span className="text-xl font-black text-rose-400 mt-1">
                {formatEuro(summary.total_spent)}
              </span>
              <span className="text-[10px] text-slate-500 mt-0.5">
                Ingresos: {formatEuro(summary.total_income)}
              </span>
            </div>

            <div className="bg-slate-900/90 border border-slate-800/80 rounded-2xl p-3 flex flex-col justify-between">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Disponible</span>
              <span
                className={`text-xl font-black mt-1 ${
                  summary.remaining_budget >= 0 ? "text-emerald-400" : "text-amber-400"
                }`}
              >
                {formatEuro(summary.remaining_budget)}
              </span>
              <span className="text-[10px] text-slate-500 mt-0.5">Restante global</span>
            </div>
          </div>

          {/* Bloque Regla 50/30/20 */}
          <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-3 flex flex-col gap-3">
            <div className="flex items-center justify-between pb-1 border-b border-slate-800">
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-bold text-slate-200">Ejecución 50 / 30 / 20</span>
              </div>
              <span className="text-[10px] text-slate-400">Objetivo Saludable</span>
            </div>

            {/* Necesidades 50% */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-300">🛒 Necesidades (50%)</span>
                <span className="text-slate-400 font-mono text-[11px]">
                  {formatEuro(summary.needs.spent)} / {formatEuro(summary.needs.budget)}
                </span>
              </div>
              <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    summary.needs.progress_percentage > 100 ? "bg-rose-500" : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.min(summary.needs.progress_percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>{summary.needs.progress_percentage.toFixed(0)}% consumido</span>
                <span>Restante: {formatEuro(summary.needs.remaining)}</span>
              </div>
            </div>

            {/* Deseos 30% */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-300">☕ Deseos (30%)</span>
                <span className="text-slate-400 font-mono text-[11px]">
                  {formatEuro(summary.wants.spent)} / {formatEuro(summary.wants.budget)}
                </span>
              </div>
              <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${
                    summary.wants.progress_percentage > 100 ? "bg-amber-500" : "bg-violet-400"
                  }`}
                  style={{ width: `${Math.min(summary.wants.progress_percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>{summary.wants.progress_percentage.toFixed(0)}% consumido</span>
                <span>Restante: {formatEuro(summary.wants.remaining)}</span>
              </div>
            </div>

            {/* Ahorro 20% */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-slate-300">📈 Ahorro e Inversión (20%)</span>
                <span className="text-slate-400 font-mono text-[11px]">
                  {formatEuro(summary.savings.spent)} / {formatEuro(summary.savings.budget)}
                </span>
              </div>
              <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
                <div
                  className="h-full bg-cyan-400 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(summary.savings.progress_percentage, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>{summary.savings.progress_percentage.toFixed(0)}% alcanzado</span>
                <span>Meta mensual: {formatEuro(summary.savings.budget)}</span>
              </div>
            </div>
          </div>

          {/* Tarjeta del Fondo de Emergencia */}
          <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-3 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck
                  className={`w-5 h-5 ${
                    summary.emergency_fund.is_funded ? "text-emerald-400" : "text-amber-400"
                  }`}
                />
                <span className="text-xs font-bold text-slate-200">Fondo de Seguridad</span>
              </div>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                  summary.emergency_fund.is_funded
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                }`}
              >
                {summary.emergency_fund.months_covered.toFixed(1)} meses
              </span>
            </div>

            <div className="flex items-baseline justify-between pt-1">
              <span className="text-sm font-extrabold text-slate-100 font-mono">
                {formatEuro(summary.emergency_fund.current_amount)}
              </span>
              <span className="text-xs text-slate-500">
                Objetivo: {formatEuro(summary.emergency_fund.target_amount)} (3 meses)
              </span>
            </div>
          </div>

          {/* Ajuste de Presupuesto por Subcategoría */}
          <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-3 flex flex-col gap-2 mb-2">
            <div className="flex items-center justify-between pb-1 border-b border-slate-800">
              <span className="text-xs font-bold text-slate-200">Presupuestos por Categoría</span>
              <span className="text-[10px] text-slate-400">Pulsa ✏️ para editar</span>
            </div>

            <div className="flex flex-col gap-1.5 divide-y divide-slate-850">
              {summary.subcategories.map((subcat) => {
                const isEditing = editingSubcatId === subcat.subcategory_id;
                return (
                  <div
                    key={subcat.subcategory_id}
                    className="pt-2 flex items-center justify-between text-xs"
                  >
                    <div className="flex flex-col">
                      <span className="font-semibold text-slate-200">{subcat.subcategory_name}</span>
                      <span className="text-[10px] text-slate-500">
                        Gastado: {formatEuro(subcat.spent)}
                      </span>
                    </div>

                    {isEditing ? (
                      <div className="flex items-center gap-1.5">
                        <input
                          type="number"
                          step="1"
                          value={editAmountStr}
                          onChange={(e: ChangeEvent<HTMLInputElement>) => setEditAmountStr(e.target.value)}
                          className="w-16 bg-slate-950 border border-emerald-500 rounded-lg px-1.5 py-1 text-xs text-slate-100 text-right focus:outline-none"
                          autoFocus
                        />
                        <button
                          type="button"
                          onClick={() => handleSaveBudget(subcat.subcategory_id)}
                          disabled={savingBudget}
                          className="p-1 rounded-lg bg-emerald-500 text-slate-950 active:scale-95"
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
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-slate-300 font-semibold">
                          {formatEuro(subcat.budget)}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleStartEdit(subcat)}
                          className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 active:scale-95"
                          title="Modificar presupuesto"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>
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
