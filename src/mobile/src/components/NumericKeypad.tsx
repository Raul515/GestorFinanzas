import { Delete } from "lucide-react";

interface NumericKeypadProps {
  amountString: string;
  onChangeAmount: (newAmountString: string) => void;
}

export const NumericKeypad = ({
  amountString,
  onChangeAmount,
}: NumericKeypadProps) => {
  const triggerHaptic = (ms: number = 10) => {
    if (typeof navigator !== "undefined" && navigator.vibrate) {
      navigator.vibrate(ms);
    }
  };

  const handleKeyPress = (key: string) => {
    triggerHaptic();

    if (key === ",") {
      if (amountString.includes(",")) return;
      onChangeAmount(amountString ? `${amountString},` : "0,");
      return;
    }

    if (key === "backspace") {
      if (amountString.length <= 1) {
        onChangeAmount("0");
      } else {
        onChangeAmount(amountString.slice(0, -1));
      }
      return;
    }

    // Si actualmente es "0", reemplazar por la cifra tecleada
    if (amountString === "0") {
      onChangeAmount(key);
      return;
    }

    // Máximo 2 decimales si ya hay coma
    if (amountString.includes(",")) {
      const parts = amountString.split(",");
      if (parts[1] && parts[1].length >= 2) {
        return;
      }
    }

    // Limitar a máximo 8 caracteres
    if (amountString.length >= 8) return;

    onChangeAmount(`${amountString}${key}`);
  };

  const handleQuickAdd = (euros: number) => {
    triggerHaptic(15);
    const normalized = amountString.replace(",", ".");
    const current = parseFloat(normalized) || 0;
    const nextVal = (current + euros).toFixed(2).replace(".", ",");
    // Si termina en ,00 y queremos número limpio, podemos conservarlo
    onChangeAmount(nextVal.endsWith(",00") ? nextVal.replace(",00", "") : nextVal);
  };

  const keys = [
    ["1", "2", "3"],
    ["4", "5", "6"],
    ["7", "8", "9"],
    [",", "0", "backspace"],
  ];

  return (
    <div className="flex flex-col gap-1.5 w-full max-w-sm mx-auto">
      {/* Botones rápidos de incremento */}
      <div className="grid grid-cols-5 gap-1.5 px-0.5">
        {[1, 2, 5, 10, 20].map((val) => (
          <button
            key={val}
            type="button"
            onClick={() => handleQuickAdd(val)}
            className="py-1 rounded-xl bg-[#0F172A] border border-white/[0.08] text-[11px] font-bold text-emerald-400 hover:text-emerald-300 active:scale-95 active:bg-emerald-950/60 active:border-emerald-500/40 transition-all shadow-sm"
          >
            +{val}€
          </button>
        ))}
      </div>

      {/* Cuadrícula numérico 3x4 con elevación táctil */}
      <div className="grid grid-cols-3 gap-1.5 p-0.5">
        {keys.flat().map((k, idx) => {
          const isBackspace = k === "backspace";
          const isComma = k === ",";
          return (
            <button
              key={idx}
              type="button"
              onClick={() => handleKeyPress(k)}
              className={`h-12 sm:h-14 rounded-2xl flex items-center justify-center font-bold transition-all select-none shadow-[0_2px_6px_rgba(0,0,0,0.35)] ${
                isBackspace
                  ? "bg-[#141E30] text-rose-400 border border-rose-500/20 active:bg-rose-950/40 active:scale-95 text-xl"
                  : isComma
                  ? "bg-[#10192A] text-slate-300 border border-white/[0.07] active:bg-[#1A263D] active:scale-95 text-3xl pb-1"
                  : "bg-[#10192A] text-slate-100 border border-white/[0.07] active:bg-[#1A263D] active:border-emerald-500/30 active:scale-95 text-2xl"
              }`}
            >
              {isBackspace ? <Delete className="w-5 h-5" /> : k}
            </button>
          );
        })}
      </div>
    </div>
  );
};
