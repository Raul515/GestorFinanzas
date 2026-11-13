import React from "react";
import { Zap, ListOrdered } from "lucide-react";
import { ActiveTab } from "../types";

interface NavigationBarProps {
  activeTab: ActiveTab;
  onChangeTab: (tab: ActiveTab) => void;
  pendingCount: number;
}

export const NavigationBar: React.FC<NavigationBarProps> = ({
  activeTab,
  onChangeTab,
  pendingCount,
}) => {
  return (
    <nav className="w-full bg-slate-900/90 backdrop-blur-md border-t border-slate-800 py-1.5 px-6 flex items-center justify-around shrink-0 max-w-sm mx-auto select-none">
      {/* Pestaña 1: Captura Rápida */}
      <button
        type="button"
        onClick={() => onChangeTab("capture")}
        className={`flex flex-col items-center gap-1 py-1 px-4 rounded-xl transition-all ${
          activeTab === "capture"
            ? "text-emerald-400 font-bold scale-105"
            : "text-slate-400 hover:text-slate-200"
        }`}
      >
        <Zap className="w-5 h-5 fill-current" />
        <span className="text-[11px]">Captura</span>
      </button>

      {/* Pestaña 2: Historial y Cola */}
      <button
        type="button"
        onClick={() => onChangeTab("history")}
        className={`relative flex flex-col items-center gap-1 py-1 px-4 rounded-xl transition-all ${
          activeTab === "history"
            ? "text-emerald-400 font-bold scale-105"
            : "text-slate-400 hover:text-slate-200"
        }`}
      >
        <div className="relative">
          <ListOrdered className="w-5 h-5" />
          {pendingCount > 0 && (
            <span className="absolute -top-1.5 -right-2 bg-amber-400 text-slate-950 font-extrabold text-[10px] w-4 h-4 rounded-full flex items-center justify-center animate-pulse">
              {pendingCount > 9 ? "9+" : pendingCount}
            </span>
          )}
        </div>
        <span className="text-[11px]">Historial</span>
      </button>
    </nav>
  );
};
