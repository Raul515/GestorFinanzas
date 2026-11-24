import { Zap, ListOrdered, PieChart, Search } from "lucide-react";
import { ActiveTab } from "../types";

interface NavigationBarProps {
  activeTab: ActiveTab;
  onChangeTab: (tab: ActiveTab) => void;
  pendingCount: number;
}

export const NavigationBar = ({
  activeTab,
  onChangeTab,
  pendingCount,
}: NavigationBarProps) => {
  const tabs = [
    {
      id: "capture" as ActiveTab,
      label: "Captura",
      icon: Zap,
      hasFill: true,
    },
    {
      id: "search" as ActiveTab,
      label: "Buscar",
      icon: Search,
      hasFill: false,
    },
    {
      id: "history" as ActiveTab,
      label: "Historial",
      icon: ListOrdered,
      hasFill: false,
      badge: pendingCount,
    },
    {
      id: "summary" as ActiveTab,
      label: "Mi Mes",
      icon: PieChart,
      hasFill: false,
    },
  ];

  return (
    <nav className="w-full dock-blur border-t border-white/[0.08] shadow-[0_-8px_30px_rgba(0,0,0,0.65)] pt-1.5 pb-[max(env(safe-area-inset-bottom,0px),10px)] px-3 flex items-center justify-around shrink-0 max-w-sm mx-auto select-none z-30 transition-all">
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        const IconComponent = tab.icon;

        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChangeTab(tab.id)}
            className={`relative flex flex-col items-center justify-center gap-1 min-h-[46px] py-1 px-3 rounded-2xl transition-all duration-200 active:scale-95 ${
              isActive
                ? "bg-emerald-500/[0.12] text-emerald-400 border border-emerald-500/25 shadow-[0_0_12px_rgba(16,185,129,0.2)]"
                : "text-slate-400 hover:text-slate-200 border border-transparent"
            }`}
          >
            <div className="relative flex items-center justify-center">
              <IconComponent
                className={`w-[19px] h-[19px] transition-transform duration-200 ${
                  isActive
                    ? `scale-110 ${tab.hasFill ? "fill-emerald-400" : ""}`
                    : "opacity-80"
                }`}
              />

              {tab.badge !== undefined && tab.badge > 0 && (
                <span className="absolute -top-1.5 -right-2.5 bg-amber-400 text-slate-950 font-black text-[9px] h-4 min-w-[16px] px-1 rounded-full flex items-center justify-center shadow-md shadow-amber-500/30 ring-2 ring-[#070B12] animate-pulse">
                  {tab.badge > 9 ? "9+" : tab.badge}
                </span>
              )}
            </div>

            <span
              className={`text-[10px] tracking-tight transition-all duration-200 ${
                isActive ? "font-extrabold text-emerald-400" : "font-medium text-slate-400"
              }`}
            >
              {tab.label}
            </span>
          </button>
        );
      })}
    </nav>
  );
};

