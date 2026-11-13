import React from "react";
import { RefreshCw, Trash2, CheckCircle2, Clock, Download, ArrowUpRight } from "lucide-react";
import { MobileTransaction } from "../types";
import { getSubcategoryEmoji } from "./CategoryChips";

interface HistoryViewProps {
  transactions: MobileTransaction[];
  isSyncing: boolean;
  onTriggerSync: () => void;
  onDeletePending: (eventId: string) => void;
  onExportJson: () => void;
}

export const HistoryView: React.FC<HistoryViewProps> = ({
  transactions,
  isSyncing,
  onTriggerSync,
  onDeletePending,
  onExportJson,
}) => {
  const pendingTx = transactions.filter((t) => t.status === "PENDING_SYNC");
  const syncedTx = transactions.filter((t) => t.status === "SYNCED");

  const formatDateDisplay = (isoDate: string) => {
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
  };

  return (
    <div className="flex-1 flex flex-col max-w-sm mx-auto w-full px-3 py-3 overflow-y-auto no-scrollbar gap-4">
      {/* Tarjeta de Estado de Sincronización */}
      <div className="p-3.5 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col gap-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Estado de la Cola</div>
            <div className="text-lg font-bold text-slate-100 flex items-center gap-2">
              {pendingTx.length > 0 ? (
                <>
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse"></span>
                  <span>{pendingTx.length} pendientes</span>
                </>
              ) : (
                <>
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                  <span className="text-emerald-400">Al día (0 pendientes)</span>
                </>
              )}
            </div>
          </div>

          <button
            type="button"
            disabled={isSyncing || pendingTx.length === 0}
            onClick={onTriggerSync}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition-all shadow-sm ${
              pendingTx.length > 0
                ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 active:scale-95"
                : "bg-slate-850 text-slate-500 cursor-not-allowed"
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin" : ""}`} />
            <span>{isSyncing ? "Enviando..." : "Sincronizar"}</span>
          </button>
        </div>

        {/* Botón de exportación JSON opcional */}
        <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
          <span>Copia de seguridad en disco</span>
          <button
            type="button"
            onClick={onExportJson}
            className="flex items-center gap-1 text-slate-300 hover:text-emerald-400 active:underline py-1"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Descargar JSON</span>
          </button>
        </div>
      </div>

      {/* Sección 1: Gastos Pendientes de Sincronizar */}
      <div>
        <div className="flex items-center justify-between px-1 mb-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>Pendientes de Enviar ({pendingTx.length})</span>
          </h4>
        </div>

        {pendingTx.length === 0 ? (
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/60 text-center text-xs text-slate-500">
            No hay gastos pendientes en la cola local.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {pendingTx.map((tx) => {
              const emoji = getSubcategoryEmoji(tx.subcategory_name);
              return (
                <div
                  key={tx.event_id}
                  className="p-3 rounded-xl bg-slate-900 border border-amber-500/30 flex items-center justify-between gap-3 shadow-sm"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-lg shrink-0">{emoji}</span>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-100 truncate">
                        {tx.description}
                      </div>
                      <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
                        <span>{tx.subcategory_name}</span>
                        <span>•</span>
                        <span>{formatDateDisplay(tx.date)}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-mono font-bold text-sm text-amber-300">
                      -{tx.amount.toFixed(2)} €
                    </span>
                    <button
                      type="button"
                      title="Eliminar gasto pendiente"
                      onClick={() => onDeletePending(tx.event_id)}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 active:bg-slate-800 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Sección 2: Gastos Recientes Confirmados */}
      <div>
        <div className="flex items-center justify-between px-1 mb-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Confirmados en el Ordenador ({syncedTx.length})</span>
          </h4>
        </div>

        {syncedTx.length === 0 ? (
          <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/60 text-center text-xs text-slate-500">
            Los gastos sincronizados aparecerán aquí.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {syncedTx.slice(0, 10).map((tx) => {
              const emoji = getSubcategoryEmoji(tx.subcategory_name);
              return (
                <div
                  key={tx.event_id}
                  className="p-2.5 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-base shrink-0">{emoji}</span>
                    <div className="min-w-0">
                      <div className="font-medium text-slate-200 truncate">{tx.description}</div>
                      <div className="text-[10px] text-slate-500">
                        {tx.subcategory_name} • {formatDateDisplay(tx.date)}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 font-mono font-semibold text-slate-300 shrink-0">
                    <span>-{tx.amount.toFixed(2)} €</span>
                    <ArrowUpRight className="w-3 h-3 text-emerald-500" />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
