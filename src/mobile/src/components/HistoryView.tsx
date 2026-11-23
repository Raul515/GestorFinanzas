import { useState } from "react";
import { RefreshCw, Trash2, CheckCircle2, Clock, Download, ArrowUpRight, AlertTriangle, Camera, X } from "lucide-react";
import { MobileTransaction } from "../types";
import { getSubcategoryEmoji } from "./CategoryChips";
import { getReceiptImageUrl } from "../services/api";

interface HistoryViewProps {
  transactions: MobileTransaction[];
  isSyncing: boolean;
  onTriggerSync: () => void;
  onDeleteTransaction: (tx: MobileTransaction) => void;
  onExportJson: () => void;
}

export const HistoryView = ({
  transactions,
  isSyncing,
  onTriggerSync,
  onDeleteTransaction,
  onExportJson,
}: HistoryViewProps) => {
  const [txToDelete, setTxToDelete] = useState<MobileTransaction | null>(null);
  const [viewingReceipt, setViewingReceipt] = useState<string | null>(null);

  const pendingTx = transactions.filter((t) => t.status === "PENDING_SYNC");
  const syncedTx = transactions.filter((t) => t.status === "SYNCED");
  const totalMonthSpent = transactions.reduce((sum, t) => sum + t.amount, 0);

  const formatDateDisplay = (isoDate: string) => {
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
  };

  const handleConfirmDelete = () => {
    if (txToDelete) {
      onDeleteTransaction(txToDelete);
      setTxToDelete(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col max-w-sm mx-auto w-full px-3 py-3 overflow-y-auto no-scrollbar gap-4 relative">
      {/* Tarjeta de Resumen y Estado de Sincronización */}
      <div className="p-3.5 rounded-2xl bg-slate-900 border border-slate-800 flex flex-col gap-3 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Total Registrado en Móvil</div>
            <div className="text-xl font-black text-slate-100 font-mono">
              -{totalMonthSpent.toFixed(2)} €
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
            <span>{isSyncing ? "Enviando..." : pendingTx.length > 0 ? `Subir (${pendingTx.length})` : "Al día"}</span>
          </button>
        </div>

        {/* Botón de exportación JSON opcional */}
        <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400">
          <span className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${pendingTx.length > 0 ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`}
            />
            <span>{pendingTx.length > 0 ? `${pendingTx.length} pendientes` : "Todo sincronizado"}</span>
          </span>
          <button
            type="button"
            onClick={onExportJson}
            className="flex items-center gap-1 text-slate-300 hover:text-emerald-400 active:underline py-1"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Exportar JSON</span>
          </button>
        </div>
      </div>

      {/* Sección 1: Gastos Pendientes de Sincronizar */}
      <div>
        <div className="flex items-center justify-between px-1 mb-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>Pendientes de Subir ({pendingTx.length})</span>
          </h4>
        </div>

        {pendingTx.length === 0 ? (
          <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800/60 text-center text-xs text-slate-500">
            No hay gastos pendientes en la memoria local.
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
                    {tx.receipt_base64 && (
                      <button
                        type="button"
                        onClick={() => setViewingReceipt(tx.receipt_base64 || null)}
                        className="p-1.5 rounded-lg text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 active:scale-95 transition-all"
                        title="Ver foto del ticket"
                      >
                        <Camera className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <span className={`font-mono font-bold text-sm ${tx.type === "INCOME" ? "text-emerald-400" : "text-amber-300"}`}>
                      {tx.type === "INCOME" ? "+" : "-"}{tx.amount.toFixed(2)} €
                    </span>
                    <button
                      type="button"
                      title="Eliminar gasto"
                      onClick={() => setTxToDelete(tx)}
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

      {/* Sección 2: Gastos Sincronizados y Confirmados */}
      <div>
        <div className="flex items-center justify-between px-1 mb-2">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Confirmados en Base de Datos ({syncedTx.length})</span>
          </h4>
        </div>

        {syncedTx.length === 0 ? (
          <div className="p-3.5 rounded-xl bg-slate-900/40 border border-slate-800/60 text-center text-xs text-slate-500">
            Los gastos ya subidos al PC aparecerán aquí.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {syncedTx.map((tx) => {
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

                  <div className="flex items-center gap-2 shrink-0">
                    {(tx.receipt_base64 || tx.receipt_filename) && (
                      <button
                        type="button"
                        onClick={() =>
                          setViewingReceipt(
                            tx.receipt_base64 || getReceiptImageUrl(tx.receipt_filename) || null
                          )
                        }
                        className="p-1 rounded-lg text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 active:scale-95 transition-all"
                        title="Ver foto del ticket"
                      >
                        <Camera className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <div className="flex items-center gap-1 font-mono font-semibold">
                      <span className={tx.type === "INCOME" ? "text-emerald-400 font-bold" : "text-slate-300"}>
                        {tx.type === "INCOME" ? "+" : "-"}{tx.amount.toFixed(2)} €
                      </span>
                      <ArrowUpRight className={`w-3 h-3 ${tx.type === "INCOME" ? "text-emerald-400" : "text-emerald-500"}`} />
                    </div>
                    <button
                      type="button"
                      title="Eliminar gasto sincronizado"
                      onClick={() => setTxToDelete(tx)}
                      className="p-1 rounded text-slate-600 hover:text-rose-400 active:bg-slate-800 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal Táctil de Confirmación de Borrado */}
      {txToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-xs rounded-2xl bg-slate-900 border border-rose-500/40 p-5 shadow-2xl flex flex-col gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-rose-500/20 text-rose-400 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-100">¿Eliminar gasto?</h3>
                <p className="text-[11px] text-slate-400">
                  {txToDelete.status === "PENDING_SYNC"
                    ? "Se borrará de la memoria local del teléfono."
                    : "Se revertirá en la base de datos del ordenador."}
                </p>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-slate-200 truncate">{txToDelete.description}</div>
                <div className="text-[10px] text-slate-400">{txToDelete.subcategory_name} • {formatDateDisplay(txToDelete.date)}</div>
              </div>
              <div className="text-sm font-black font-mono text-rose-400 shrink-0">
                -{txToDelete.amount.toFixed(2)} €
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1">
              <button
                type="button"
                onClick={() => setTxToDelete(null)}
                className="py-2.5 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition-all active:scale-95"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                className="py-2.5 px-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all shadow-md shadow-rose-900/40 active:scale-95 flex items-center justify-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Eliminar</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Visor de Comprobante / Ticket (Fase 12) */}
      {viewingReceipt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-slate-950/90 backdrop-blur-md animate-fade-in">
          <div className="w-full max-w-sm rounded-2xl bg-slate-900 border border-slate-800 p-3 shadow-2xl flex flex-col gap-3 max-h-[90vh]">
            <div className="flex items-center justify-between pb-1 border-b border-slate-800">
              <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                <Camera className="w-4 h-4 text-emerald-400" />
                <span>Comprobante de Ticket</span>
              </span>
              <button
                type="button"
                onClick={() => setViewingReceipt(null)}
                className="p-1 rounded-full text-slate-400 hover:text-slate-100 active:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-auto rounded-xl bg-slate-950 flex items-center justify-center p-1 border border-slate-800">
              <img
                src={viewingReceipt}
                alt="Ticket completo"
                className="max-h-[70vh] w-auto max-w-full object-contain rounded-lg shadow-sm"
              />
            </div>
            <button
              type="button"
              onClick={() => setViewingReceipt(null)}
              className="w-full py-2 rounded-xl bg-slate-800 text-slate-200 text-xs font-bold active:scale-95"
            >
              Cerrar
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

