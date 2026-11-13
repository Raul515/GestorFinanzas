import { useState, useEffect, useCallback } from "react";
import { QuickCaptureView } from "./components/QuickCaptureView";
import { HistoryView } from "./components/HistoryView";
import { NavigationBar } from "./components/NavigationBar";
import { ActiveTab, MobileTransaction } from "./types";
import {
  loadStoredTransactions,
  saveStoredTransactions,
  loadStoredCatalog,
  saveStoredCatalog,
  exportTransactionsToJsonFile,
} from "./services/storage";
import {
  fetchCatalog,
  syncTransactionsWithBackend,
  checkServerStatus,
} from "./services/api";

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("capture");
  const [catalog, setCatalog] = useState(loadStoredCatalog);
  const [transactions, setTransactions] = useState<MobileTransaction[]>(loadStoredTransactions);
  const [isServerOnline, setIsServerOnline] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);

  const pendingCount = transactions.filter((t) => t.status === "PENDING_SYNC").length;

  // Comprobar conectividad y refrescar catálogo
  const refreshConnectivityAndCatalog = useCallback(async () => {
    const online = await checkServerStatus();
    setIsServerOnline(online);

    if (online) {
      const remoteCatalog = await fetchCatalog();
      if (remoteCatalog) {
        setCatalog(remoteCatalog);
        saveStoredCatalog(remoteCatalog);
      }
    }
  }, []);

  // Función de sincronización con el backend
  const handleTriggerSync = useCallback(async () => {
    const pending = transactions.filter((t) => t.status === "PENDING_SYNC");
    if (pending.length === 0 || isSyncing) return;

    setIsSyncing(true);
    try {
      const result = await syncTransactionsWithBackend(pending);
      if (result && result.success) {
        // Marcar todas las pendientes como sincronizadas
        setTransactions((prev) => {
          const updated = prev.map((t) =>
            t.status === "PENDING_SYNC" ? { ...t, status: "SYNCED" as const } : t
          );
          saveStoredTransactions(updated);
          return updated;
        });
        setIsServerOnline(true);
      } else {
        setIsServerOnline(false);
      }
    } catch {
      setIsServerOnline(false);
    } finally {
      setIsSyncing(false);
    }
  }, [transactions, isSyncing]);

  // Al montar la app: comprobar servidor e intentar auto-sync si hay pendientes
  useEffect(() => {
    refreshConnectivityAndCatalog();

    const interval = setInterval(() => {
      refreshConnectivityAndCatalog();
    }, 15000);

    return () => clearInterval(interval);
  }, [refreshConnectivityAndCatalog]);

  // Auto-sync al detectar servidor online si hay pendientes
  useEffect(() => {
    if (isServerOnline && pendingCount > 0 && !isSyncing) {
      handleTriggerSync();
    }
  }, [isServerOnline, pendingCount, isSyncing, handleTriggerSync]);

  const handleSaveExpense = (newTx: MobileTransaction) => {
    setTransactions((prev) => {
      const updated = [newTx, ...prev];
      saveStoredTransactions(updated);
      return updated;
    });

    // Intentar sincronizar inmediatamente si estamos conectados
    if (isServerOnline) {
      setTimeout(() => {
        handleTriggerSync();
      }, 300);
    }
  };

  const handleDeletePending = (eventId: string) => {
    setTransactions((prev) => {
      const updated = prev.filter((t) => t.event_id !== eventId);
      saveStoredTransactions(updated);
      return updated;
    });
  };

  const handleExportJson = () => {
    exportTransactionsToJsonFile(transactions);
  };

  return (
    <div className="h-full flex flex-col bg-slate-950 text-slate-100 select-none overflow-hidden font-sans">
      {/* Barra superior de estado */}
      <header className="px-4 py-2 border-b border-slate-900 flex items-center justify-between shrink-0 max-w-sm mx-auto w-full">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50"></div>
          <span className="font-extrabold text-sm tracking-tight text-slate-200">
            Gestor Finanzas
          </span>
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            MÓVIL
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400">
          <span
            className={`w-2 h-2 rounded-full ${
              isServerOnline ? "bg-emerald-400" : "bg-slate-600"
            }`}
          ></span>
          <span>{isServerOnline ? "En línea" : "Offline"}</span>
        </div>
      </header>

      {/* Contenido principal según pestaña activa */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {activeTab === "capture" ? (
          <QuickCaptureView
            subcategories={catalog.personal_subcategories}
            frequentConcepts={catalog.frequent_concepts}
            onSaveExpense={handleSaveExpense}
          />
        ) : (
          <HistoryView
            transactions={transactions}
            isSyncing={isSyncing}
            onTriggerSync={handleTriggerSync}
            onDeletePending={handleDeletePending}
            onExportJson={handleExportJson}
          />
        )}
      </main>

      {/* Barra de navegación inferior */}
      <NavigationBar
        activeTab={activeTab}
        onChangeTab={(tab) => setActiveTab(tab)}
        pendingCount={pendingCount}
      />
    </div>
  );
}

export default App;
