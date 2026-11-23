import { useState, ChangeEvent } from "react";
import { Zap, Calendar, CheckCircle2 } from "lucide-react";
import { NumericKeypad } from "./NumericKeypad";
import { CategoryChips } from "./CategoryChips";
import { ConceptSuggestions } from "./ConceptSuggestions";
import { SubcategoryItem, MobileTransaction } from "../types";

interface QuickCaptureViewProps {
  subcategories: SubcategoryItem[];
  frequentConcepts: string[];
  onSaveExpense: (tx: MobileTransaction) => void;
  onCreateSubcategory?: (name: string, categoryName: string) => Promise<SubcategoryItem | null> | SubcategoryItem | null;
}

export const QuickCaptureView = ({
  subcategories,
  frequentConcepts,
  onSaveExpense,
  onCreateSubcategory,
}: QuickCaptureViewProps) => {
  const [amountStr, setAmountStr] = useState("0");
  const [selectedSubcat, setSelectedSubcat] = useState<SubcategoryItem | null>(() => {
    return subcategories.find((s) => s.is_frequent) || subcategories[0] || null;
  });
  const [concept, setConcept] = useState("");
  const [selectedDate, setSelectedDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [showToast, setShowToast] = useState(false);

  // Parsear importe numérico
  const numericAmount = parseFloat(amountStr.replace(",", ".")) || 0;
  const canSave = numericAmount > 0 && selectedSubcat !== null;

  const handleSave = () => {
    if (!canSave || !selectedSubcat) return;

    if (typeof navigator !== "undefined" && navigator.vibrate) {
      navigator.vibrate(40);
    }

    const newTx: MobileTransaction = {
      event_id: `mob-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      scope: "PERSONAL",
      amount: Math.round(numericAmount * 100) / 100,
      description: concept.trim() || selectedSubcat.name,
      date: selectedDate,
      subcategory_id: selectedSubcat.id,
      subcategory_name: selectedSubcat.name,
      created_at_utc: new Date().toISOString(),
      status: "PENDING_SYNC",
    };

    onSaveExpense(newTx);

    // Resetear formulario inmediatamente (< 100 ms)
    setAmountStr("0");
    setConcept("");
    setShowToast(true);
    setTimeout(() => setShowToast(false), 2000);
  };

  // Formatear fecha para mostrar
  const formatDateDisplay = (isoDate: string) => {
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
  };

  return (
    <div className="flex-1 flex flex-col justify-between max-w-sm mx-auto w-full px-3 py-2 overflow-y-auto no-scrollbar">
      {/* Toast de confirmación rápida */}
      {showToast && (
        <div className="fixed top-3 left-1/2 -translate-x-1/2 z-50 bg-emerald-500 text-slate-950 font-bold px-4 py-2 rounded-full shadow-lg flex items-center gap-2 text-xs animate-in fade-in slide-in-from-top-4 duration-150">
          <CheckCircle2 className="w-4 h-4" />
          <span>¡Gasto guardado correctamente!</span>
        </div>
      )}

      {/* Cabecera compacta: Ámbito y Selector de Fecha */}
      <div className="flex items-center justify-between pb-1 pt-0.5">
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-[11px] font-semibold text-emerald-400">
          <span>👤</span>
          <span>Cuenta Personal</span>
        </div>

        <label className="relative inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-[11px] font-medium text-slate-300 cursor-pointer active:bg-slate-850">
          <Calendar className="w-3.5 h-3.5 text-slate-400" />
          <span>{formatDateDisplay(selectedDate)}</span>
          <input
            type="date"
            value={selectedDate}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSelectedDate(e.target.value)}
            className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
          />
        </label>
      </div>

      {/* Display del Importe en Pantalla */}
      <div className="flex flex-col items-center justify-center my-1 py-1">
        <div className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-0.5">
          Importe del Gasto
        </div>
        <div className="flex items-baseline justify-center gap-1 text-slate-100 font-mono select-none">
          <span className="text-2xl font-light text-slate-500">€</span>
          <span className="text-4xl sm:text-5xl font-extrabold tracking-tight text-emerald-400">
            {amountStr}
          </span>
        </div>
      </div>

      {/* Selector de Chips de Categorías */}
      <div className="my-1">
        <CategoryChips
          subcategories={subcategories}
          selectedSubcategoryId={selectedSubcat?.id || null}
          onSelectSubcategory={(subcat) => setSelectedSubcat(subcat)}
          onCreateSubcategory={onCreateSubcategory}
        />
      </div>

      {/* Campo de Concepto y Sugerencias */}
      <div className="my-1">
        <ConceptSuggestions
          concept={concept}
          onChangeConcept={(val) => setConcept(val)}
          frequentConcepts={frequentConcepts}
        />
      </div>

      {/* Teclado Numérico */}
      <div className="my-1">
        <NumericKeypad
          amountString={amountStr}
          onChangeAmount={(val) => setAmountStr(val)}
        />
      </div>

      {/* Botón Prominente de Guardado */}
      <div className="pt-2 pb-1">
        <button
          type="button"
          disabled={!canSave}
          onClick={handleSave}
          className={`w-full py-3.5 rounded-2xl flex items-center justify-center gap-2 font-bold text-base transition-all select-none shadow-md ${
            canSave
              ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20 active:scale-[0.98] active:bg-emerald-600"
              : "bg-slate-900 border border-slate-800 text-slate-600 cursor-not-allowed opacity-60"
          }`}
        >
          <Zap className="w-5 h-5 fill-current" />
          <span>
            {canSave
              ? `Guardar Gasto (${amountStr} €)`
              : "Introduce un importe"}
          </span>
        </button>
      </div>
    </div>
  );
};
