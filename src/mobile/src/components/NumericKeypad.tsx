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
    <div className="flex flex-col gap-2 w-full max-w-sm mx-auto">
      {/* Botones rápidos de incremento */}
      <div className="grid grid-cols-5 gap-1.5 px-1">
        {[1, 2, 5, 10, 20].map((val) => (
          <button
            key={val}
            type="button"
            onClick={() => handleQuickAdd(val)}
            className="py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-semibold text-emerald-400 active:scale-95 active:bg-emerald-950/60 active:border-emerald-600 transition-transform"
          >
            +{val}€
          </button>
        ))}
      </div>

      {/* Cuadrícula numérico 3x4 */}
      <div className="grid grid-cols-3 gap-2 p-1">
        {keys.flat().map((k, idx) => {
          const isBackspace = k === "backspace";
          return (
            <button
              key={idx}
              type="button"
              onClick={() => handleKeyPress(k)}
              className={`h-14 sm:h-16 rounded-xl flex items-center justify-center font-bold text-2xl transition-all select-none shadow-sm ${
                isBackspace
                  ? "bg-slate-900/90 text-rose-400 border border-slate-800/80 active:bg-rose-950/50"
                  : k === ","
                  ? "bg-slate-900 text-slate-300 border border-slate-800 active:bg-slate-800 text-3xl pb-2"
                  : "bg-slate-900 text-slate-100 border border-slate-800 active:bg-slate-800 active:scale-95 text-2xl"
              }`}
            >
              {isBackspace ? <Delete className="w-6 h-6" /> : k}
            </button>
          );
        })}
      </div>
    </div>
  );
};
