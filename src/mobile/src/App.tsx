import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Capacitor } from "@capacitor/core";
import { Browser } from "@capacitor/browser";
import { QuickCaptureView } from "./components/QuickCaptureView";
import { SearchView } from "./components/SearchView";
import { HistoryView } from "./components/HistoryView";
import { MonthlySummaryView } from "./components/MonthlySummaryView";
import { NavigationBar } from "./components/NavigationBar";
import { ServerConfigModal } from "./components/ServerConfigModal";
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
  isIOSDevice,
  getStoredPairingToken,
  saveStoredPairingToken,
  clearStoredPairingToken,
  loadStoredPendingDeletes,
  addPendingDelete,
  removePendingDelete,
  saveStoredMonthlySummary,
  loadStoredMonthlySummariesMap,
  upsertStoredMonthlySummary,
  loadStoredHistoryCache,
  saveStoredHistoryCache,
  getStoredServerUrl,
  saveStoredServerUrl,
  clearStoredServerUrl,
  extractAndSaveServerUrlFromUrl,
  isIncomeSubcategory,
} from "./services/storage";
import {
  computeOfflineMonthlySummary,
  overlayPendingTransactionsOnSummary,
} from "./services/offlineEngine";
import { getLocalMonthString } from "./utils/formatters";
import {
  getBaseApiUrl,
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
import { Settings } from "lucide-react";

const APP_VERSION_NAME = typeof __APP_VERSION__ !== "undefined" ? __APP_VERSION__ : "1.4.0";
const CURRENT_APP_VERSION = { code: 14, name: APP_VERSION_NAME };

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("capture");
  const [catalog, setCatalog] = useState(loadStoredCatalog);
  const [transactions, setTransactions] = useState<MobileTransaction[]>(loadStoredTransactions);
  const [rawSummariesMap, setMonthlySummariesMap] = useState(loadStoredMonthlySummariesMap);
  const [historyCache, setHistoryCache] = useState<HistoricalTransactionItem[]>(loadStoredHistoryCache);
  const [isServerOnline, setIsServerOnline] = useState(false);
  const [isPaired, setIsPaired] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [availableUpdate, setAvailableUpdate] = useState<MobileVersionInfo | null>(null);
  const [latestApkInfo, setLatestApkInfo] = useState<MobileVersionInfo | null>(null);
  const [otaBannerDismissed, setOtaBannerDismissed] = useState(false);

  const monthlySummariesMap = useMemo(() => {
    const currentMonth = getLocalMonthString();
    const baseCurrent =
      rawSummariesMap[currentMonth] ||
      computeOfflineMonthlySummary(currentMonth, [], catalog.personal_subcategories);
    const enriched: Record<string, typeof baseCurrent> = {
      ...rawSummariesMap,
      [currentMonth]: baseCurrent,
    };
    const result: Record<string, typeof baseCurrent> = {};
    Object.entries(enriched).forEach(([mKey, summary]) => {
      result[mKey] = overlayPendingTransactionsOnSummary(
        summary,
        transactions,
        catalog.personal_subcategories
      );
    });
    return result;
  }, [rawSummariesMap, transactions, catalog.personal_subcategories]);

  const monthlySummary = monthlySummariesMap[getLocalMonthString()] || null;

  // Modal / Diálogo para configurar la URL del servidor y el token de emparejamiento
  const [showServerConfigModal, setShowServerConfigModal] = useState(false);
  const lastDataFetchRef = useRef<number>(0);

  const pendingCount = transactions.filter((t) => t.status === "PENDING_SYNC").length;

  // Extraer token y servidor de URL si vienen en la query string (?token=... o ?server=...)
  useEffect(() => {
    extractAndSavePairingTokenFromUrl();
    extractAndSaveServerUrlFromUrl();
  }, []);

  // Adaptar variable --vvh a visualViewport para que iOS Safari ajuste modales sobre el teclado virtual
  useEffect(() => {
    const syncVvh = () => {
      if (typeof window !== "undefined" && window.visualViewport && typeof document !== "undefined") {
        document.documentElement.style.setProperty("--vvh", `${window.visualViewport.height}px`);
      }
    };
    if (typeof window !== "undefined" && window.visualViewport) {
      window.visualViewport.addEventListener("resize", syncVvh);
      window.visualViewport.addEventListener("scroll", syncVvh);
      syncVvh();
      return () => {
        window.visualViewport?.removeEventListener("resize", syncVvh);
        window.visualViewport?.removeEventListener("scroll", syncVvh);
      };
    }
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
        saveStoredMonthlySummary(remoteSummary);
        setMonthlySummariesMap(upsertStoredMonthlySummary(remoteSummary));
      }

      const remoteHistory = await fetchHistoryCache(12);
      if (remoteHistory !== null) {
        setHistoryCache(remoteHistory);
        saveStoredHistoryCache(remoteHistory);

        // Reconciliación bidireccional: purgar transacciones SYNCED eliminadas desde PC/Streamlit
        const serverEventIds = new Set(
          remoteHistory.map((t) => t.mobile_event_id).filter(Boolean) as string[]
        );
        const serverDates = remoteHistory.map((t) => t.date).filter(Boolean).sort();
        const minServerDate = serverDates.length > 0 ? serverDates[0] : null;

        setTransactions((prev) => {
          const reconciled = prev.filter((t) => {
            if (t.status !== "SYNCED") return true;
            if (minServerDate && t.date >= minServerDate) {
              return serverEventIds.has(t.event_id);
            }
            return true;
          });
          if (reconciled.length !== prev.length) {
            saveStoredTransactions(reconciled);
            return reconciled;
          }
          return prev;
        });
      }
    } catch (e) {
      console.warn("Fallo en sincronización secundaria de datos móviles:", e);
    }
  }, []);

  // Comprobar conectividad y estado básico de salud de forma ligera
  const checkConnectivity = useCallback(async (): Promise<boolean> => {
    // Pausar sondeo si la pestaña móvil está en segundo plano para ahorrar batería y red
    if (typeof document !== "undefined" && document.visibilityState !== "visible") {
      return isServerOnline;
    }

    try {
      const wasOnline = isServerOnline;
      const status = await checkServerStatus();
      setIsServerOnline(status.isOnline);
      setIsPaired(status.isPaired);

      if (status.isOnline && status.isPaired) {
        if (!wasOnline || lastDataFetchRef.current === 0) {
          refreshHeavyData(true);
        }

        // Comprobar disponibilidad de APK en el servidor (solo Android)
        if (!isIOSDevice()) {
          const versionInfo = await fetchLatestVersion();
          if (versionInfo && versionInfo.apk_available) {
            setLatestApkInfo(versionInfo);
            // El banner superior OTA solo se muestra en la APK nativa instalada cuando hay una versión superior
            if (Capacitor.isNativePlatform() && versionInfo.version_code > CURRENT_APP_VERSION.code) {
              setAvailableUpdate(versionInfo);
            } else {
              setAvailableUpdate(null);
            }
          } else {
            setLatestApkInfo(null);
            setAvailableUpdate(null);
          }
        } else {
          setLatestApkInfo(null);
          setAvailableUpdate(null);
        }
      }
      return status.isOnline;
    } catch {
      setIsServerOnline(false);
      return false;
    }
  }, [isServerOnline, refreshHeavyData]);

  // Función de sincronización con el backend
  const handleTriggerSync = useCallback(async () => {
    const pending = transactions.filter((t) => t.status === "PENDING_SYNC");
    const pendingDeletes = loadStoredPendingDeletes();
    if ((pending.length === 0 && pendingDeletes.length === 0) || isSyncing) return;

    setIsSyncing(true);
    try {
      // 1. Procesar borrados pendientes de sincronizar
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

      if (pending.length === 0) {
        refreshHeavyData(true);
        return;
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
        setShowServerConfigModal(true);
      } else if (result && result.isValidationError) {
        // Mitigación de Cola Envenenada (HTTP 422): evitar reintentos infinitos
        setTransactions((prev) => {
          const updated = prev.map((t) =>
            t.status === "PENDING_SYNC" ? { ...t, status: "SYNC_ERROR" as const } : t
          );
          saveStoredTransactions(updated);
          return updated;
        });
      } else {
        setIsServerOnline(false);
      }
    } catch {
      setIsServerOnline(false);
    } finally {
      setIsSyncing(false);
    }
  }, [transactions, isSyncing, refreshHeavyData]);

  // Sondeo adaptativo cada 60s con pausa en segundo plano y reconexión inmediata al volver Wi-Fi
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
    const handleOnline = () => {
      checkConnectivity();
    };
    const handleOffline = () => {
      setIsServerOnline(false);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [checkConnectivity]);

  // Refrescar datos pesados al cambiar de pestaña si están obsoletos
  useEffect(() => {
    if (
      (activeTab === "summary" || activeTab === "history" || activeTab === "search") &&
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

    // Intentar sincronizar inmediatamente si estamos conectados y emparejados
    if (isServerOnline && isPaired) {
      setTimeout(() => {
        handleTriggerSync();
      }, 300);
    }
  };

  const handleDeleteTransaction = async (tx: MobileTransaction) => {
    // Buscar la versión actual en memoria (puede haber pasado a SYNCED antes de pulsar Deshacer)
    const liveTx = transactions.find((t) => t.event_id === tx.event_id) || tx;

    // 1. Eliminar inmediatamente del estado y almacenamiento local
    setTransactions((prev) => {
      const updated = prev.filter((t) => t.event_id !== liveTx.event_id);
      saveStoredTransactions(updated);
      return updated;
    });

    // Revertir incremento optimista de Deseos si aplica
    if (liveTx.status === "SYNCED" && liveTx.type !== "INCOME" && monthlySummary?.wants) {
      const isWants = catalog.personal_subcategories.some(
        (s) => s.id === liveTx.subcategory_id && (s.category_name.toLowerCase().includes("deseo") || s.category_id === 3)
      );
      if (isWants && liveTx.amount > 0) {
        const baseForMonth = rawSummariesMap[monthlySummary.month] || monthlySummary;
        const newSpent = Math.max(0, baseForMonth.wants.spent - liveTx.amount);
        const updatedSummary = {
          ...baseForMonth,
          wants: {
            ...baseForMonth.wants,
            spent: newSpent,
            remaining: baseForMonth.wants.budget - newSpent,
          },
        };
        saveStoredMonthlySummary(updatedSummary);
        setMonthlySummariesMap(upsertStoredMonthlySummary(updatedSummary));
      }
    }

    // 2. Si la transacción ya estaba subida al servidor, solicitar borrado remoto o encolarlo
    if (liveTx.status === "SYNCED") {
      if (isServerOnline && isPaired) {
        try {
          const ok = await deleteMobileTransaction(liveTx.event_id);
          if (!ok) {
            addPendingDelete(liveTx.event_id);
          }
        } catch {
          addPendingDelete(liveTx.event_id);
        }
      } else {
        addPendingDelete(liveTx.event_id);
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

    // Si estamos offline o falló la conexión, crear con ID temporal negativo y tipo correcto
    const isIncome = isIncomeSubcategory({ category_name: categoryName });
    const tempSubcat: SubcategoryItem = {
      id: -Date.now(),
      name,
      category_id: isIncome ? 1 : categoryName.includes("50%") ? 2 : categoryName.includes("20%") ? 4 : 3,
      category_name: categoryName,
      category_type: isIncome ? "income" : "expense",
      is_frequent: true,
    };
    const updatedCat = addSubcategoryToStoredCatalog(tempSubcat);
    setCatalog(updatedCat);
    return tempSubcat;
  };

  const handleSaveServerConfig = (newServerUrl: string, newPairingToken: string) => {
    if (newServerUrl) {
      saveStoredServerUrl(newServerUrl);
    } else {
      clearStoredServerUrl();
    }
    if (newPairingToken) {
      saveStoredPairingToken(newPairingToken);
    } else {
      clearStoredPairingToken();
    }
    lastDataFetchRef.current = 0;
    checkConnectivity();
    refreshHeavyData(true);
  };

  const handleOpenOtaDownload = async () => {
    const url = getApkDownloadUrl();
    if (Capacitor.isNativePlatform()) {
      try {
        await Browser.open({ url });
        return;
      } catch (err) {
        console.warn("Fallo al abrir descarga OTA con Browser plugin, usando window.open:", err);
      }
    }
    window.open(url, "_blank");
  };

  return (
    <div className="h-full flex flex-col bg-[#070B12] text-slate-100 select-none overflow-hidden font-sans">
      {/* Barra superior de estado con soporte Safe-Area */}
      <header className="pt-[max(env(safe-area-inset-top,0px),10px)] pb-2.5 px-4 border-b border-white/[0.06] bg-[#070B12]/85 backdrop-blur-md flex items-center justify-between shrink-0 max-w-sm mx-auto w-full z-20">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
          <span className="font-black text-[13.5px] tracking-tight text-slate-100">
            Gestor Finanzas
          </span>
          <span className="text-[9px] font-extrabold px-1.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 tracking-wider">
            MÓVIL v{CURRENT_APP_VERSION.name}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] font-medium">
          <button
            type="button"
            onClick={() => setShowServerConfigModal(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900/90 border border-white/[0.08] hover:border-slate-700 active:scale-95 transition-all text-slate-300 shadow-sm"
            title="Configurar servidor y token de conexión"
          >
            <span
              className={`w-2 h-2 rounded-full ${
                isServerOnline
                  ? isPaired
                    ? "bg-emerald-400 shadow-[0_0_6px_#34d399]"
                    : "bg-amber-400 shadow-[0_0_6px_#fbbf24]"
                  : "bg-slate-600"
              }`}
            />
            <span className="text-[10.5px] font-bold">
              {isServerOnline ? (isPaired ? "En línea" : "Sin enlazar") : "Offline"}
            </span>
            <Settings className="w-3.5 h-3.5 text-slate-400 ml-0.5 transition-transform active:rotate-45" />
          </button>
        </div>
      </header>

      {/* Banner de Actualización OTA disponible (solo APK nativa) */}
      {availableUpdate && !otaBannerDismissed && (
        <div className="bg-emerald-500/20 border-b border-emerald-500/30 px-3.5 py-1.5 flex items-center justify-between text-xs text-emerald-300 shrink-0">
          <div className="flex items-center gap-1.5 font-medium">
            <span>🚀</span>
            <span>Nueva versión v{availableUpdate.version_name}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleOpenOtaDownload}
              className="px-2.5 py-0.5 rounded-lg bg-emerald-500 text-slate-950 font-extrabold text-[11px] active:scale-95 shadow-sm"
            >
              Actualizar
            </button>
            <button
              type="button"
              onClick={() => setOtaBannerDismissed(true)}
              className="px-1.5 py-0.5 rounded-lg text-emerald-300/70 hover:text-emerald-200 font-bold text-xs"
              title="Ocultar aviso"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Contenido principal según pestaña activa con scroll elástico y min-h-0 */}
      <main className="flex-1 min-h-0 flex flex-col overflow-y-auto overflow-x-hidden">
        {activeTab === "capture" ? (
          <QuickCaptureView
            subcategories={catalog.personal_subcategories}
            frequentConcepts={catalog.frequent_concepts}
            monthlySummary={monthlySummary}
            monthlySummariesMap={monthlySummariesMap}
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
          <MonthlySummaryView
            isServerOnline={isServerOnline}
            transactions={transactions}
            subcategories={catalog.personal_subcategories}
            cachedSummariesMap={monthlySummariesMap}
            onSummaryLoaded={(loaded) => {
              const updatedMap = upsertStoredMonthlySummary(loaded);
              setMonthlySummariesMap(updatedMap);
            }}
            onRequestReconnect={checkConnectivity}
          />
        )}
      </main>

      {/* Barra de navegación inferior */}
      <NavigationBar
        activeTab={activeTab}
        onChangeTab={(tab) => setActiveTab(tab)}
        pendingCount={pendingCount}
      />

      {/* Modal de Configuración de Servidor Backend y Token */}
      <ServerConfigModal
        isOpen={showServerConfigModal}
        onClose={() => setShowServerConfigModal(false)}
        currentServerUrl={getStoredServerUrl() || getBaseApiUrl()}
        currentPairingToken={getStoredPairingToken() || ""}
        isOnline={isServerOnline}
        isPaired={isPaired}
        onSave={handleSaveServerConfig}
        latestApkInfo={latestApkInfo}
        onDownloadApk={handleOpenOtaDownload}
      />
    </div>
  );
}

export default App;
