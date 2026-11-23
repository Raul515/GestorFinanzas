import { useState, useEffect, useCallback, useRef, ChangeEvent } from "react";
import { QuickCaptureView } from "./components/QuickCaptureView";
import { SearchView } from "./components/SearchView";
import { HistoryView } from "./components/HistoryView";
import { MonthlySummaryView } from "./components/MonthlySummaryView";
import { NavigationBar } from "./components/NavigationBar";
import {
  ActiveTab,
  HistoricalTransactionItem,
  MobileTransaction,
  MobileVersionInfo,
  SubcategoryItem,
} from "./types";
import {
  loadStoredTransactions,
  saveStoredTransactions,
  loadStoredCatalog,
  saveStoredCatalog,
  addSubcategoryToStoredCatalog,
  exportTransactionsToJsonFile,
  extractAndSavePairingTokenFromUrl,
  getStoredPairingToken,
  saveStoredPairingToken,
  loadStoredPendingDeletes,
  addPendingDelete,
  removePendingDelete,
  loadStoredMonthlySummary,
  saveStoredMonthlySummary,
  loadStoredHistoryCache,
  saveStoredHistoryCache,
} from "./services/storage";
import {
  fetchCatalog,
  syncTransactionsWithBackend,
  checkServerStatus,
  createSubcategoryOnTheFly,
  fetchLatestVersion,
  getApkDownloadUrl,
  deleteMobileTransaction,
  fetchMonthlySummary,
  searchMobileTransactions,
  fetchHistoryCache,
} from "./services/api";
import { ShieldAlert, KeyRound, Check, X } from "lucide-react";

const CURRENT_APP_VERSION = { code: 1, name: "1.0.0" };

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("capture");
  const [catalog, setCatalog] = useState(loadStoredCatalog);
  const [transactions, setTransactions] = useState<MobileTransaction[]>(loadStoredTransactions);
  const [monthlySummary, setMonthlySummary] = useState(loadStoredMonthlySummary);
  const [historyCache, setHistoryCache] = useState<HistoricalTransactionItem[]>(loadStoredHistoryCache);
  const [isServerOnline, setIsServerOnline] = useState(false);
  const [isPaired, setIsPaired] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [availableUpdate, setAvailableUpdate] = useState<MobileVersionInfo | null>(null);

  // Modal / Diálogo para introducir el pairing token si no coincide o falta
  const [showPairingModal, setShowPairingModal] = useState(false);
  const [inputToken, setInputToken] = useState("");
  const lastDataFetchRef = useRef<number>(0);

  const pendingCount = transactions.filter((t) => t.status === "PENDING_SYNC").length;

  // Extraer token de URL si viene en la query string (?token=...)
  useEffect(() => {
    extractAndSavePairingTokenFromUrl();
  }, []);

  // Carga desacoplada de catálogo, resumen mensual e histórico (solo bajo demanda o arranque)
  const refreshHeavyData = useCallback(async (force = false) => {
    const now = Date.now();
    if (!force && now - lastDataFetchRef.current < 60000) {
      return;
    }
    lastDataFetchRef.current = now;

    try {
      const remoteCatalog = await fetchCatalog();
      if (remoteCatalog) {
        setCatalog(remoteCatalog);
        saveStoredCatalog(remoteCatalog);
      }

      const remoteSummary = await fetchMonthlySummary();
      if (remoteSummary) {
        setMonthlySummary(remoteSummary);
        saveStoredMonthlySummary(remoteSummary);
      }

      const remoteHistory = await fetchHistoryCache(12);
      if (remoteHistory && remoteHistory.length > 0) {
        setHistoryCache(remoteHistory);
        saveStoredHistoryCache(remoteHistory);
      }
    } catch (e) {
      console.warn("Fallo en sincronización secundaria de datos móviles:", e);
    }
  }, []);

  // Comprobar conectividad y estado básico de salud de forma ligera
  const checkConnectivity = useCallback(async () => {
    // Pausar sondeo si la pestaña móvil está en segundo plano para ahorrar batería y red
    if (typeof document !== "undefined" && document.visibilityState !== "visible") {
      return;
    }

    try {
      const status = await checkServerStatus();
      setIsServerOnline(status.isOnline);
      setIsPaired(status.isPaired);

      if (status.isOnline && status.isPaired) {
        if (lastDataFetchRef.current === 0) {
          refreshHeavyData();
        }

        // Comprobar si hay una nueva versión de APK para auto-actualización OTA
        const versionInfo = await fetchLatestVersion();
        if (
          versionInfo &&
          versionInfo.version_code > CURRENT_APP_VERSION.code &&
          versionInfo.apk_available
        ) {
          setAvailableUpdate(versionInfo);
        } else {
          setAvailableUpdate(null);
        }
      }
    } catch {
      setIsServerOnline(false);
    }
  }, [refreshHeavyData]);

  // Función de sincronización con el backend
  const handleTriggerSync = useCallback(async () => {
    const pending = transactions.filter((t) => t.status === "PENDING_SYNC");
    if (pending.length === 0 || isSyncing) return;

    setIsSyncing(true);
    try {
      // 1. Procesar borrados pendientes de sincronizar
      const pendingDeletes = loadStoredPendingDeletes();
      if (pendingDeletes.length > 0) {
        for (const delId of pendingDeletes) {
          try {
            const ok = await deleteMobileTransaction(delId);
            if (ok) {
              removePendingDelete(delId);
            }
          } catch {
            // Reintento en el siguiente ciclo
          }
        }
      }

      // 2. Ingestar transacciones nuevas en cola
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
        setIsPaired(true);
        // Refrescar reactivamente tras la mutación exitosa
        refreshHeavyData(true);
      } else if (result && result.isUnauthorized) {
        setIsPaired(false);
        setShowPairingModal(true);
      } else {
        setIsServerOnline(false);
      }
    } catch {
      setIsServerOnline(false);
    } finally {
      setIsSyncing(false);
    }
  }, [transactions, isSyncing, refreshHeavyData]);

  // Sondeo adaptativo cada 60s con pausa en segundo plano
  useEffect(() => {
    checkConnectivity();

    const interval = setInterval(() => {
      checkConnectivity();
    }, 60000);

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        checkConnectivity();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [checkConnectivity]);

  // Refrescar datos pesados al cambiar de pestaña si están obsoletos
  useEffect(() => {
    if (
      (activeTab === "month" || activeTab === "history" || activeTab === "search") &&
      isServerOnline &&
      isPaired
    ) {
      refreshHeavyData();
    }
  }, [activeTab, isServerOnline, isPaired, refreshHeavyData]);

  // Auto-sync al detectar servidor online si hay pendientes y estamos emparejados
  useEffect(() => {
    if (isServerOnline && isPaired && pendingCount > 0 && !isSyncing) {
      handleTriggerSync();
    }
  }, [isServerOnline, isPaired, pendingCount, isSyncing, handleTriggerSync]);

  const handleSaveExpense = (newTx: MobileTransaction) => {
    setTransactions((prev) => {
      const updated = [newTx, ...prev];
      saveStoredTransactions(updated);
      return updated;
    });

    // Actualización optimista del gasto de Deseos para que el semáforo refleje el apunte al instante
    if (newTx.subcategory_name && monthlySummary?.wants) {
      const isWants = catalog.personal_subcategories.some(
        (s) => s.id === newTx.subcategory_id && (s.category_name.toLowerCase().includes("deseo") || s.category_id === 3)
      );
      if (isWants) {
        const newSpent = monthlySummary.wants.spent + newTx.amount;
        const updatedSummary = {
          ...monthlySummary,
          wants: {
            ...monthlySummary.wants,
            spent: newSpent,
            remaining: monthlySummary.wants.budget - newSpent,
          },
        };
        setMonthlySummary(updatedSummary);
        saveStoredMonthlySummary(updatedSummary);
      }
    }

    // Intentar sincronizar inmediatamente si estamos conectados y emparejados
    if (isServerOnline && isPaired) {
      setTimeout(() => {
        handleTriggerSync();
      }, 300);
    }
  };

  const handleDeleteTransaction = async (tx: MobileTransaction) => {
    // 1. Eliminar inmediatamente del estado y almacenamiento local
    setTransactions((prev) => {
      const updated = prev.filter((t) => t.event_id !== tx.event_id);
      saveStoredTransactions(updated);
      return updated;
    });

    // 2. Si la transacción ya estaba subida al servidor, solicitar borrado remoto o encolarlo
    if (tx.status === "SYNCED") {
      if (isServerOnline && isPaired) {
        try {
          const ok = await deleteMobileTransaction(tx.event_id);
          if (!ok) {
            addPendingDelete(tx.event_id);
          }
        } catch {
          addPendingDelete(tx.event_id);
        }
      } else {
        addPendingDelete(tx.event_id);
      }
    }
  };

  const handleExportJson = () => {
    exportTransactionsToJsonFile(transactions);
  };

  const handleSearchServer = useCallback(
    async (query: string): Promise<HistoricalTransactionItem[]> => {
      if (!isServerOnline || !isPaired) return [];
      const res = await searchMobileTransactions(query, 50);
      return res?.items || [];
    },
    [isServerOnline, isPaired]
  );

  const handleCreateSubcategory = async (
    name: string,
    categoryName: string
  ): Promise<SubcategoryItem | null> => {
    // Si estamos en línea y emparejados, crearla en el backend
    if (isServerOnline && isPaired) {
      const remote = await createSubcategoryOnTheFly(name, categoryName);
      if (remote) {
        const updatedCat = addSubcategoryToStoredCatalog(remote);
        setCatalog(updatedCat);
        return remote;
      }
    }

    // Si estamos offline o falló la conexión, crear con ID temporal negativo
    const tempSubcat: SubcategoryItem = {
      id: -Date.now(),
      name,
      category_id: categoryName.includes("50%") ? 2 : 3,
      category_name: categoryName,
      is_frequent: true,
    };
    const updatedCat = addSubcategoryToStoredCatalog(tempSubcat);
    setCatalog(updatedCat);
    return tempSubcat;
  };

  const handleSaveManualToken = () => {
    if (inputToken.trim()) {
      saveStoredPairingToken(inputToken.trim());
      setShowPairingModal(false);
      setInputToken("");
      refreshConnectivityAndCatalog();
    }
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

        <div className="flex items-center gap-2 text-[11px] font-medium">
          {!isPaired && isServerOnline ? (
            <button
              type="button"
              onClick={() => setShowPairingModal(true)}
              className="flex items-center gap-1 text-amber-400 font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 active:scale-95"
            >
              <KeyRound className="w-3 h-3" />
              <span>No Vinculado</span>
            </button>
          ) : (
            <div className="flex items-center gap-1.5 text-slate-400">
              <span
                className={`w-2 h-2 rounded-full ${isServerOnline ? "bg-emerald-400" : "bg-slate-600"
                  }`}
              ></span>
              <span>{isServerOnline ? "En línea" : "Offline"}</span>
            </div>
          )}
        </div>
      </header>

      {/* Banner de Actualización OTA disponible */}
      {availableUpdate && (
        <div className="bg-emerald-500/20 border-b border-emerald-500/30 px-3.5 py-1.5 flex items-center justify-between text-xs text-emerald-300 shrink-0">
          <div className="flex items-center gap-1.5 font-medium">
            <span>🚀</span>
            <span>Nueva versión v{availableUpdate.version_name}</span>
          </div>
          <button
            type="button"
            onClick={() => window.open(getApkDownloadUrl(), "_blank")}
            className="px-2.5 py-0.5 rounded-lg bg-emerald-500 text-slate-950 font-extrabold text-[11px] active:scale-95 shadow-sm"
          >
            Actualizar
          </button>
        </div>
      )}

      {/* Contenido principal según pestaña activa */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {activeTab === "capture" ? (
          <QuickCaptureView
            subcategories={catalog.personal_subcategories}
            frequentConcepts={catalog.frequent_concepts}
            monthlySummary={monthlySummary}
            onSaveExpense={handleSaveExpense}
            onDeleteExpense={(eventId) => handleDeleteTransaction({ event_id: eventId } as MobileTransaction)}
            onCreateSubcategory={handleCreateSubcategory}
          />
        ) : activeTab === "search" ? (
          <SearchView
            isServerOnline={isServerOnline}
            frequentConcepts={catalog.frequent_concepts}
            localTransactions={transactions}
            historyCache={historyCache}
            onSearchServer={handleSearchServer}
          />
        ) : activeTab === "history" ? (
          <HistoryView
            transactions={transactions}
            isSyncing={isSyncing}
            onTriggerSync={handleTriggerSync}
            onDeleteTransaction={handleDeleteTransaction}
            onExportJson={handleExportJson}
          />
        ) : (
          <MonthlySummaryView isServerOnline={isServerOnline} />
        )}
      </main>

      {/* Barra de navegación inferior */}
      <NavigationBar
        activeTab={activeTab}
        onChangeTab={(tab) => setActiveTab(tab)}
        pendingCount={pendingCount}
      />

      {/* Modal de Token de Emparejamiento (para APK o reconexión) */}
      {showPairingModal && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex flex-col justify-center p-4 animate-in fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-sm mx-auto w-full p-4 flex flex-col gap-3 shadow-2xl">
            <div className="flex items-center justify-between pb-1 border-b border-slate-800">
              <div className="flex items-center gap-2 text-amber-400">
                <ShieldAlert className="w-5 h-5" />
                <h3 className="font-bold text-sm text-slate-100">Vincular con tu PC</h3>
              </div>
              <button
                type="button"
                onClick={() => setShowPairingModal(false)}
                className="p-1 text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Para proteger tu base de datos contra dispositivos ajenos conectados a tu Wi-Fi, introduce el Token de Emparejamiento generado en la app de PC (en <strong>Ajustes &gt; Companion Móvil</strong>):
            </p>

            <div className="flex flex-col gap-1.5">
              <input
                type="text"
                value={inputToken}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setInputToken(e.target.value)}
                placeholder="sec_..."
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-100 font-mono focus:outline-none focus:border-emerald-500"
              />
              {getStoredPairingToken() && (
                <span className="text-[10px] text-slate-500 font-mono truncate">
                  Token actual: {getStoredPairingToken()?.substring(0, 12)}...
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowPairingModal(false)}
                className="flex-1 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-semibold"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleSaveManualToken}
                disabled={!inputToken.trim()}
                className="flex-1 py-2 rounded-xl bg-emerald-500 text-slate-950 text-xs font-bold active:bg-emerald-400 disabled:opacity-50 flex items-center justify-center gap-1.5"
              >
                <Check className="w-4 h-4" />
                <span>Guardar Token</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
