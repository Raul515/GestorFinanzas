import { useState, useRef, ChangeEvent } from "react";
import { Zap, Calendar, CheckCircle2, AlertTriangle, Sparkles, Camera, X } from "lucide-react";
import { NumericKeypad } from "./NumericKeypad";
import { CategoryChips } from "./CategoryChips";
import { ConceptSuggestions } from "./ConceptSuggestions";
import { QuickPresetChips } from "./QuickPresetChips";
import { ManagePresetsModal } from "./ManagePresetsModal";
import { SubcategoryItem, MobileTransaction, MobileMonthlySummary, QuickPresetItem } from "../types";
import { loadStoredQuickPresets, saveStoredQuickPresets } from "../services/storage";

interface QuickCaptureViewProps {
  subcategories: SubcategoryItem[];
  frequentConcepts: string[];
  monthlySummary?: MobileMonthlySummary | null;
  onSaveExpense: (tx: MobileTransaction) => void;
  onDeleteExpense?: (eventId: string) => void;
  onCreateSubcategory?: (name: string, categoryName: string) => Promise<SubcategoryItem | null> | SubcategoryItem | null;
}

export const QuickCaptureView = ({
  subcategories,
  frequentConcepts,
  monthlySummary,
  onSaveExpense,
  onDeleteExpense,
  onCreateSubcategory,
}: QuickCaptureViewProps) => {
  const [txType, setTxType] = useState<"EXPENSE" | "INCOME">("EXPENSE");
  const [amountStr, setAmountStr] = useState("0");
  const [selectedSubcat, setSelectedSubcat] = useState<SubcategoryItem | null>(() => {
    return subcategories.find((s) => s.is_frequent) || subcategories[0] || null;
  });
  const [concept, setConcept] = useState("");
  const [selectedDate, setSelectedDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [receiptBase64, setReceiptBase64] = useState<string | null>(null);
  const [toastInfo, setToastInfo] = useState<{ message: string; eventId?: string } | null>(null);
  const [presets, setPresets] = useState<QuickPresetItem[]>(loadStoredQuickPresets);
  const [isManageModalOpen, setIsManageModalOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleTypeSwitch = (type: "EXPENSE" | "INCOME") => {
    setTxType(type);
    const relevantSubcats = subcategories.filter((s) =>
      type === "INCOME"
        ? s.category_type === "income" || s.category_name.toLowerCase().includes("ingreso")
        : s.category_type !== "income" && !s.category_name.toLowerCase().includes("ingreso")
    );
    setSelectedSubcat(relevantSubcats.find((s) => s.is_frequent) || relevantSubcats[0] || null);
  };

  // Captura y compresión client-side en Canvas HTML5 (< 200 KB)
  const handlePhotoCapture = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const img = new Image();
      img.onload = () => {
        const maxDim = 1280;
        let width = img.width;
        let height = img.height;
        if (width > height && width > maxDim) {
          height = Math.round((height * maxDim) / width);
          width = maxDim;
        } else if (height > maxDim) {
          width = Math.round((width * maxDim) / height);
          height = maxDim;
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(img, 0, 0, width, height);
          const compressed = canvas.toDataURL("image/jpeg", 0.7);
          setReceiptBase64(compressed);
        }
      };
      if (typeof event.target?.result === "string") {
        img.src = event.target.result;
      }
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  // Parsear importe numérico
  const numericAmount = parseFloat(amountStr.replace(",", ".")) || 0;
  const canSave = numericAmount > 0 && selectedSubcat !== null;

  // Lógica predictiva del semáforo de Deseos (30%) - solo aplica en modo Gasto
  const isWants =
    txType === "EXPENSE" &&
    selectedSubcat !== null &&
    (selectedSubcat.category_name.toLowerCase().includes("deseo") || selectedSubcat.category_id === 3);

  const wantsBudget = monthlySummary?.wants?.budget || 0;
  const currentWantsSpent = monthlySummary?.wants?.spent || 0;

  let wantsAlert = null;
  if (isWants && wantsBudget > 0) {
    const projectedSpent = currentWantsSpent + numericAmount;
    const remainingAfter = wantsBudget - projectedSpent;
    const projectedRatio = projectedSpent / wantsBudget;

    if (projectedRatio >= 1.0) {
      wantsAlert = {
        level: "OVER_LIMIT" as const,
        title: "🚨 Techo de Deseos Superado",
        desc: `Excederás tu presupuesto de ocio en ${Math.abs(remainingAfter).toFixed(2)} € (Proyectado: ${projectedSpent.toFixed(2)} € / ${wantsBudget.toFixed(2)} €)`,
        bgColor: "bg-rose-950/40",
        borderColor: "border-rose-500/60",
        textColor: "text-rose-400",
        badge: "Déficit Ocio",
        badgeClass: "bg-rose-500 text-white",
      };
    } else if (projectedRatio >= 0.80) {
      wantsAlert = {
        level: "WARNING" as const,
        title: "⚠️ Atención: Cerca del Límite",
        desc: `Quedarán solo ${remainingAfter.toFixed(2)} € disponibles de ocio este mes (${Math.round(projectedRatio * 100)}% consumido)`,
        bgColor: "bg-amber-950/40",
        borderColor: "border-amber-500/50",
        textColor: "text-amber-400",
        badge: "Consumo Alto",
        badgeClass: "bg-amber-500 text-slate-950 font-bold",
      };
    } else {
      wantsAlert = {
        level: "OPTIMAL" as const,
        title: "🟢 Margen de Ocio Saludable",
        desc: `Quedarán ${remainingAfter.toFixed(2)} € disponibles en Deseos (${Math.round(projectedRatio * 100)}% consumido)`,
        bgColor: "bg-emerald-950/20",
        borderColor: "border-emerald-500/30",
        textColor: "text-emerald-400",
        badge: "Margen OK",
        badgeClass: "bg-emerald-500/20 text-emerald-400",
      };
    }
  }

  const handleSave = () => {
    if (!canSave || !selectedSubcat) return;

    if (typeof navigator !== "undefined" && navigator.vibrate) {
      navigator.vibrate(40);
    }

    const newTx: MobileTransaction = {
      event_id: `mob-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      scope: "PERSONAL",
      type: txType,
      amount: Math.round(numericAmount * 100) / 100,
      description: concept.trim() || selectedSubcat.name,
      date: selectedDate,
      subcategory_id: selectedSubcat.id,
      subcategory_name: selectedSubcat.name,
      created_at_utc: new Date().toISOString(),
      status: "PENDING_SYNC",
      receipt_base64: receiptBase64 || undefined,
    };

    onSaveExpense(newTx);

    // Resetear formulario inmediatamente (< 100 ms)
    setAmountStr("0");
    setConcept("");
    setReceiptBase64(null);
    setToastInfo({
      message: `¡${txType === "INCOME" ? "Ingreso" : "Gasto"} guardado correctamente!`,
      eventId: newTx.event_id,
    });
    setTimeout(() => setToastInfo(null), 3000);
  };

  // Atajos Rápidos: Tap corto (precarga de formulario)
  const handleSelectPreset = (preset: QuickPresetItem) => {
    setTxType("EXPENSE");
    setAmountStr(preset.amount.toString().replace(".", ","));
    const matched = subcategories.find(
      (s) =>
        (preset.subcategory_id && s.id === preset.subcategory_id) ||
        s.name.toLowerCase() === preset.subcategory_name.toLowerCase()
    );
    if (matched) {
      setSelectedSubcat(matched);
    }
    setConcept(preset.concept || preset.name);
  };

  // Atajos Rápidos: Pulsación larga (1-Tap directo con salvaguarda)
  const handleDirectSavePreset = (preset: QuickPresetItem) => {
    const targetSubcat =
      subcategories.find(
        (s) =>
          (preset.subcategory_id && s.id === preset.subcategory_id) ||
          s.name.toLowerCase() === preset.subcategory_name.toLowerCase()
      ) ||
      selectedSubcat ||
      subcategories[0];

    if (!targetSubcat) return;

    // Salvaguarda del Techo de Presupuesto de Deseos (Fase 10)
    const isWants =
      targetSubcat.category_name.toLowerCase().includes("deseo") ||
      targetSubcat.category_id === 3;
    const wantsBudget = monthlySummary?.wants?.budget || 0;
    const currentWantsSpent = monthlySummary?.wants?.spent || 0;

    if (isWants && wantsBudget > 0) {
      const projectedSpent = currentWantsSpent + preset.amount;
      if (projectedSpent >= wantsBudget) {
        // Bloqueo de 1-Tap: precargar formulario y alertar con semáforo rojo
        if (typeof navigator !== "undefined" && navigator.vibrate) {
          navigator.vibrate([40, 60, 40]);
        }
        handleSelectPreset(preset);
        return;
      }
    }

    if (typeof navigator !== "undefined" && navigator.vibrate) {
      navigator.vibrate(40);
    }

    const newTx: MobileTransaction = {
      event_id: `mob-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      scope: "PERSONAL",
      type: "EXPENSE",
      amount: Math.round(preset.amount * 100) / 100,
      description: preset.concept.trim() || preset.name,
      date: selectedDate,
      subcategory_id: targetSubcat.id,
      subcategory_name: targetSubcat.name,
      created_at_utc: new Date().toISOString(),
      status: "PENDING_SYNC",
    };

    onSaveExpense(newTx);

    setToastInfo({
      message: `¡${preset.emoji} ${preset.name} (${preset.amount.toFixed(2).replace(".", ",")} €) guardado!`,
      eventId: newTx.event_id,
    });
    setTimeout(() => {
      setToastInfo(null);
    }, 4000);
  };

  const handleSavePresets = (updated: QuickPresetItem[]) => {
    setPresets(updated);
    saveStoredQuickPresets(updated);
  };

  // Formatear fecha para mostrar
  const formatDateDisplay = (isoDate: string) => {
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
  };

  return (
    <div className="flex-1 flex flex-col justify-between max-w-sm mx-auto w-full px-3 py-2 overflow-y-auto no-scrollbar">
      {/* Toast de confirmación rápida con soporte para Deshacer (1-Tap) */}
      {toastInfo && (
        <div className="fixed top-3 left-1/2 -translate-x-1/2 z-50 bg-emerald-500 text-slate-950 font-bold px-3.5 py-1.5 rounded-full shadow-lg flex items-center gap-2 text-xs animate-in fade-in slide-in-from-top-4 duration-150">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span className="truncate">{toastInfo.message}</span>
          {toastInfo.eventId && onDeleteExpense && (
            <button
              type="button"
              onClick={() => {
                onDeleteExpense(toastInfo.eventId!);
                setToastInfo(null);
              }}
              className="bg-slate-950 text-white font-bold px-2 py-0.5 rounded-full text-[10px] hover:bg-slate-800 active:scale-95 transition-all ml-1 shrink-0"
            >
              Deshacer
            </button>
          )}
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

      {/* Selector de Tipo: Gasto / Ingreso (Fase 13) */}
      <div className="flex bg-slate-900/90 p-1 rounded-xl border border-slate-800 gap-1 my-1">
        <button
          type="button"
          onClick={() => handleTypeSwitch("EXPENSE")}
          className={`flex-1 py-1 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
            txType === "EXPENSE"
              ? "bg-rose-500/20 text-rose-400 border border-rose-500/40 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>🔴</span>
          <span>Gasto</span>
        </button>
        <button
          type="button"
          onClick={() => handleTypeSwitch("INCOME")}
          className={`flex-1 py-1 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
            txType === "INCOME"
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <span>🟢</span>
          <span>Ingreso / Bizum</span>
        </button>
      </div>

      {/* Atajos Rápidos de Importe y Presets Frecuentes 1-Tap (Fase 14) */}
      {txType === "EXPENSE" && (
        <QuickPresetChips
          presets={presets}
          onSelectPreset={handleSelectPreset}
          onDirectSave={handleDirectSavePreset}
          onOpenManageModal={() => setIsManageModalOpen(true)}
        />
      )}

      {/* Display del Importe en Pantalla */}
      <div className="flex flex-col items-center justify-center my-1 py-1">
        <div className="text-xs uppercase tracking-wider font-semibold text-slate-500 mb-0.5">
          {txType === "INCOME" ? "Importe del Ingreso" : "Importe del Gasto"}
        </div>
        <div className="flex items-baseline justify-center gap-1 text-slate-100 font-mono select-none">
          <span className="text-2xl font-light text-slate-500">€</span>
          <span className={`text-4xl sm:text-5xl font-extrabold tracking-tight ${
            txType === "INCOME"
              ? "text-emerald-400"
              : wantsAlert?.level === "OVER_LIMIT"
              ? "text-rose-400"
              : wantsAlert?.level === "WARNING"
              ? "text-amber-400"
              : "text-emerald-400"
          }`}>
            {txType === "INCOME" ? `+${amountStr}` : amountStr}
          </span>
        </div>
      </div>

      {/* Semáforo Predictivo de Techo de Deseos (Fase 10) */}
      {wantsAlert && (
        <div
          className={`mx-1 my-1 p-2.5 rounded-xl border ${wantsAlert.borderColor} ${wantsAlert.bgColor} flex items-center justify-between gap-2 shadow-sm transition-all duration-200 animate-in fade-in`}
        >
          <div className="flex items-center gap-2 min-w-0">
            {wantsAlert.level === "OVER_LIMIT" ? (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 animate-pulse" />
            ) : wantsAlert.level === "WARNING" ? (
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            ) : (
              <Sparkles className="w-4 h-4 text-emerald-400 shrink-0" />
            )}
            <div className="min-w-0">
              <div className={`text-[11px] font-bold ${wantsAlert.textColor} leading-tight truncate`}>
                {wantsAlert.title}
              </div>
              <div className="text-[10px] text-slate-400 leading-tight truncate">
                {wantsAlert.desc}
              </div>
            </div>
          </div>
          <span className={`text-[9px] px-2 py-0.5 rounded-full font-bold uppercase shrink-0 ${wantsAlert.badgeClass}`}>
            {wantsAlert.badge}
          </span>
        </div>
      )}

      {/* Selector de Chips de Categorías */}
      <div className="my-1">
        <CategoryChips
          subcategories={
            subcategories.filter((s) =>
              txType === "INCOME"
                ? s.category_type === "income" || s.category_name.toLowerCase().includes("ingreso")
                : s.category_type !== "income" && !s.category_name.toLowerCase().includes("ingreso")
            ).length > 0
              ? subcategories.filter((s) =>
                  txType === "INCOME"
                    ? s.category_type === "income" || s.category_name.toLowerCase().includes("ingreso")
                    : s.category_type !== "income" && !s.category_name.toLowerCase().includes("ingreso")
                )
              : subcategories
          }
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

      {/* Botón / Adjunto de Foto del Ticket (Fase 12) */}
      <div className="my-1 flex items-center justify-between">
        <input
          type="file"
          accept="image/*"
          capture="environment"
          ref={fileInputRef}
          onChange={handlePhotoCapture}
          className="hidden"
        />
        {!receiptBase64 ? (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold text-slate-300 hover:text-emerald-400 active:scale-95 transition-all shadow-sm"
          >
            <Camera className="w-3.5 h-3.5 text-emerald-400" />
            <span>Foto Ticket</span>
          </button>
        ) : (
          <div className="flex-1 flex items-center justify-between px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300 animate-in fade-in">
            <div className="flex items-center gap-2 min-w-0">
              <img
                src={receiptBase64}
                alt="Ticket adjunto"
                className="w-6 h-6 object-cover rounded-md border border-emerald-500/40 shrink-0"
              />
              <span className="font-bold text-[11px] truncate">Ticket adjunto (&lt;200 KB)</span>
            </div>
            <button
              type="button"
              onClick={() => setReceiptBase64(null)}
              className="p-1 rounded-full text-slate-400 hover:text-rose-400 active:bg-slate-800"
              title="Quitar foto"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
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
              ? txType === "INCOME"
                ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20 active:scale-[0.98] active:bg-emerald-600"
                : "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20 active:scale-[0.98] active:bg-emerald-600"
              : "bg-slate-900 border border-slate-800 text-slate-600 cursor-not-allowed opacity-60"
          }`}
        >
          <Zap className="w-5 h-5 fill-current" />
          <span>
            {canSave
              ? txType === "INCOME"
                ? `Guardar Ingreso (+${amountStr} €)`
                : `Guardar Gasto (${amountStr} €)`
              : "Introduce un importe"}
          </span>
        </button>
      </div>
      {/* Modal de Gestión de Atajos Rápidos */}
      <ManagePresetsModal
        isOpen={isManageModalOpen}
        presets={presets}
        subcategories={subcategories}
        onClose={() => setIsManageModalOpen(false)}
        onSavePresets={handleSavePresets}
      />
    </div>
  );
};
