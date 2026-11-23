import { useState, useRef, TouchEvent, MouseEvent } from "react";
import { Settings2, Sparkles } from "lucide-react";
import { QuickPresetItem } from "../types";

interface QuickPresetChipsProps {
  presets: QuickPresetItem[];
  onSelectPreset: (preset: QuickPresetItem) => void;
  onDirectSave: (preset: QuickPresetItem) => void;
  onOpenManageModal: () => void;
}

export const QuickPresetChips = ({
  presets,
  onSelectPreset,
  onDirectSave,
  onOpenManageModal,
}: QuickPresetChipsProps) => {
  const [activeLongPressId, setActiveLongPressId] = useState<string | null>(null);
  const [pressProgress, setPressProgress] = useState(0);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const didTriggerLongPressRef = useRef<boolean>(false);
  const touchStartPosRef = useRef<{ x: number; y: number } | null>(null);

  const LONG_PRESS_DURATION_MS = 500;

  const triggerHaptic = (ms: number = 40) => {
    if (typeof navigator !== "undefined" && navigator.vibrate) {
      navigator.vibrate(ms);
    }
  };

  const startPress = (preset: QuickPresetItem, clientX: number, clientY: number) => {
    didTriggerLongPressRef.current = false;
    touchStartPosRef.current = { x: clientX, y: clientY };
    setActiveLongPressId(preset.id);
    startTimeRef.current = Date.now();
    setPressProgress(0);

    const updateProgress = () => {
      const elapsed = Date.now() - (startTimeRef.current ?? 0);
      const progress = Math.min(100, Math.round((elapsed / LONG_PRESS_DURATION_MS) * 100));
      setPressProgress(progress);

      if (elapsed < LONG_PRESS_DURATION_MS) {
        animFrameRef.current = requestAnimationFrame(updateProgress);
      }
    };
    animFrameRef.current = requestAnimationFrame(updateProgress);

    timerRef.current = setTimeout(() => {
      didTriggerLongPressRef.current = true;
      triggerHaptic(50);
      onDirectSave(preset);
      cancelPress(false);
    }, LONG_PRESS_DURATION_MS);
  };

  const cancelPress = (triggerTapIfShort: boolean, preset?: QuickPresetItem) => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    setActiveLongPressId(null);
    setPressProgress(0);

    if (triggerTapIfShort && !didTriggerLongPressRef.current && preset) {
      triggerHaptic(15);
      onSelectPreset(preset);
    }

    didTriggerLongPressRef.current = false;
    touchStartPosRef.current = null;
  };

  const handleTouchMove = (e: TouchEvent) => {
    if (!touchStartPosRef.current) return;
    const touch = e.touches[0];
    if (!touch) return;
    const dx = Math.abs(touch.clientX - touchStartPosRef.current.x);
    const dy = Math.abs(touch.clientY - touchStartPosRef.current.y);
    // Si el usuario se desplaza más de 10px, asume scroll horizontal y cancela
    if (dx > 10 || dy > 10) {
      cancelPress(false);
    }
  };

  return (
    <div className="w-full flex flex-col gap-1 my-1">
      {/* Fila de atajos y botón de ajustes */}
      <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5 px-0.5">
        <div className="flex items-center gap-1.5 shrink-0">
          {presets.map((p) => {
            const isPressing = activeLongPressId === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onTouchStart={(e: TouchEvent) => {
                  const t = e.touches[0];
                  if (t) startPress(p, t.clientX, t.clientY);
                }}
                onTouchEnd={() => cancelPress(true, p)}
                onTouchMove={handleTouchMove}
                onTouchCancel={() => cancelPress(false)}
                onMouseDown={(e: MouseEvent) => startPress(p, e.clientX, e.clientY)}
                onMouseUp={() => cancelPress(true, p)}
                onMouseLeave={() => cancelPress(false)}
                className={`relative overflow-hidden px-3 py-1.5 rounded-xl border text-xs font-semibold flex items-center gap-1.5 transition-all select-none shadow-sm shrink-0 active:scale-95 ${
                  isPressing
                    ? "bg-emerald-950/70 border-emerald-500 text-emerald-200 scale-95"
                    : "bg-slate-900 border-slate-800 text-slate-200 hover:border-slate-700 hover:text-white"
                }`}
                title="Toca para rellenar · Mantén pulsado para guardar directo"
              >
                {/* Barra de progreso de pulsación continua (long-press) */}
                {isPressing && (
                  <div
                    className="absolute inset-0 bg-emerald-500/30 transition-all duration-75 pointer-events-none"
                    style={{ width: `${pressProgress}%` }}
                  />
                )}
                <span className="text-sm shrink-0 relative z-10">{p.emoji}</span>
                <span className="font-bold relative z-10">{p.name}</span>
                <span className="font-mono text-emerald-400 font-bold ml-0.5 relative z-10">
                  {p.amount.toFixed(2).replace(".", ",")} €
                </span>
              </button>
            );
          })}
        </div>

        {/* Botón de configuración/gestión de atajos */}
        <button
          type="button"
          onClick={onOpenManageModal}
          className="p-1.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-emerald-400 active:scale-90 transition-all shrink-0 ml-auto"
          title="Gestionar atajos rápidos"
        >
          <Settings2 className="w-4 h-4" />
        </button>
      </div>

      {/* Micro-guía explicativa para el usuario */}
      <div className="flex items-center justify-between px-1 text-[10px] text-slate-500 font-medium">
        <span className="inline-flex items-center gap-1">
          <Sparkles className="w-2.5 h-2.5 text-emerald-400/80" />
          <span>Toca para rellenar · Mantén pulsado para 1-Tap directo</span>
        </span>
      </div>
    </div>
  );
};
