import { useState, useMemo, ChangeEvent, KeyboardEvent } from "react";
import { Search, X, Tag, Calendar, Camera } from "lucide-react";
import { HistoricalTransactionItem, MobileTransaction } from "../types";
import { getSubcategoryEmoji } from "./CategoryChips";
import { getReceiptImageUrl } from "../services/api";

interface SearchViewProps {
  isServerOnline: boolean;
  frequentConcepts: string[];
  localTransactions: MobileTransaction[];
  historyCache: HistoricalTransactionItem[];
  onSearchServer?: (query: string) => Promise<HistoricalTransactionItem[]>;
}

export const SearchView = ({
  isServerOnline,
  frequentConcepts,
  localTransactions,
  historyCache,
  onSearchServer,
}: SearchViewProps) => {
  const [query, setQuery] = useState("");
  const [serverResults, setServerResults] = useState<HistoricalTransactionItem[] | null>(null);
  const [isSearchingServer, setIsSearchingServer] = useState(false);
  const [viewingReceipt, setViewingReceipt] = useState<string | null>(null);

  // Formato español de fecha DD/MM/AAAA
  const formatDateDisplay = (isoDate: string) => {
    if (!isoDate) return "";
    const [y, m, d] = isoDate.split("-");
    return d && m && y ? `${d}/${m}/${y}` : isoDate;
  };

  // 1. Filtrado instantáneo en memoria sobre transacciones locales y caché histórica (0 ms latencia)
  const localResults = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];

    // Combinar transacciones de la cola local reciente con la caché histórica
    const combined: HistoricalTransactionItem[] = [
      ...localTransactions.map((t, idx) => ({
        id: -1 * (idx + 1),
        date: t.date,
        amount: t.amount,
        description: t.description,
        type: t.type || "EXPENSE",
        subcategory_id: t.subcategory_id || 0,
        subcategory_name: t.subcategory_name || "",
        category_name: "Cuenta Personal",
        receipt_filename: t.receipt_filename || undefined,
        receipt_url: getReceiptImageUrl(t.receipt_filename),
      })),
      ...historyCache,
    ];

    // Filtrar por concepto o por subcategoría
    const filtered = combined.filter((item) => {
      const matchDesc = item.description?.toLowerCase().includes(q);
      const matchSub = item.subcategory_name?.toLowerCase().includes(q);
      return matchDesc || matchSub;
    });

    // Ordenar por fecha descendente
    return filtered.sort((a, b) => b.date.localeCompare(a.date));
  }, [query, localTransactions, historyCache]);

  // Lista de resultados efectiva (prioriza resultados del servidor si se realizó búsqueda profunda)
  const displayResults = serverResults !== null ? serverResults : localResults;

  const handleSearchOnline = async () => {
    if (!query.trim() || !onSearchServer || !isServerOnline) return;
    setIsSearchingServer(true);
    try {
      const results = await onSearchServer(query.trim());
      setServerResults(results);
    } catch {
      // fallback a resultados locales
    } finally {
      setIsSearchingServer(false);
    }
  };

  const handleClear = () => {
    setQuery("");
    setServerResults(null);
  };

  return (
    <div className="flex-1 flex flex-col max-w-sm mx-auto w-full px-3 py-2 overflow-y-auto no-scrollbar gap-3">
      {/* Barra de Búsqueda Táctil */}
      <div className="relative flex items-center">
        <div className="absolute left-3 text-slate-400 pointer-events-none">
          <Search className="w-4 h-4" />
        </div>
        <input
          type="text"
          value={query}
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            setQuery(e.target.value);
            if (serverResults !== null) setServerResults(null);
          }}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
            if (e.key === "Enter") handleSearchOnline();
          }}
          placeholder="¿Cuánto me costó... (ej. itv, zara, taller)?"
          autoFocus
          className="w-full bg-slate-900 border border-slate-800 rounded-2xl pl-9 pr-9 py-3 text-xs text-slate-100 placeholder-slate-500 font-medium focus:outline-none focus:border-emerald-500 shadow-sm"
        />
        {query && (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-3 p-1 rounded-full text-slate-400 hover:text-slate-200 active:bg-slate-800"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Sugerencias Rápidas de Búsqueda si no hay texto */}
      {!query && (
        <div className="flex flex-col gap-2 pt-1">
          <div className="flex items-center gap-1.5 px-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider">
            <Tag className="w-3 h-3 text-emerald-400" />
            <span>Consultas Frecuentes</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[...new Set([...frequentConcepts, "Gasolina", "Supermercado", "Restaurante", "Farmacia"])]
              .slice(0, 8)
              .map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => setQuery(tag)}
                  className="px-2.5 py-1.5 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs font-medium active:scale-95 transition-all shadow-sm"
                >
                  {tag}
                </button>
              ))}
          </div>

          <div className="mt-4 p-3.5 rounded-2xl bg-slate-900/60 border border-slate-800/80 text-center flex flex-col gap-1.5 text-xs text-slate-400">
            <div className="text-sm font-bold text-slate-200">🔍 Memoria Instantánea en tu Bolsillo</div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Escribe cualquier concepto o comercio para ver cuánto pagaste la última vez, sin importar si estás en la tienda sin internet o en casa.
            </p>
          </div>
        </div>
      )}

      {/* Resultados de la Búsqueda */}
      {query && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between px-1 text-xs text-slate-400">
            <span>
              {displayResults.length} resultado{displayResults.length === 1 ? "" : "s"} para "{query}"
            </span>
            {isServerOnline && onSearchServer && serverResults === null && (
              <button
                type="button"
                disabled={isSearchingServer}
                onClick={handleSearchOnline}
                className="text-[11px] font-bold text-emerald-400 hover:underline active:opacity-70"
              >
                {isSearchingServer ? "Buscando en servidor..." : "Buscar en todo el histórico"}
              </button>
            )}
          </div>

          {displayResults.length === 0 ? (
            <div className="p-5 rounded-2xl bg-slate-900/40 border border-slate-800 text-center flex flex-col gap-1 text-xs text-slate-500">
              <span className="text-base">🔎</span>
              <span className="font-semibold text-slate-400">No se encontraron gastos</span>
              <span className="text-[11px] text-slate-500">
                No hay coincidencias en los últimos 12 meses para "{query}".
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {displayResults.map((item, index) => {
                const emoji = getSubcategoryEmoji(item.subcategory_name);
                const isLatest = index === 0;

                return (
                  <div
                    key={`${item.id}-${index}`}
                    className={`p-3 rounded-2xl bg-slate-900 border flex items-center justify-between gap-3 shadow-sm transition-all ${
                      isLatest ? "border-emerald-500/40 bg-slate-900/90" : "border-slate-800/80"
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="text-xl shrink-0">{emoji}</span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm font-bold text-slate-100 truncate">
                            {item.description}
                          </span>
                          {isLatest && (
                            <span className="px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[9px] font-extrabold uppercase shrink-0">
                              Último
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-400 flex items-center gap-1.5 mt-0.5">
                          <span className="truncate">{item.subcategory_name}</span>
                          <span>•</span>
                          <span className="flex items-center gap-1 shrink-0 font-medium">
                            <Calendar className="w-3 h-3 text-slate-500" />
                            {formatDateDisplay(item.date)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {(item.receipt_filename || item.receipt_url) && (
                        <button
                          type="button"
                          onClick={() => setViewingReceipt(getReceiptImageUrl(item.receipt_filename || item.receipt_url) ?? null)}
                          className="p-1 rounded-lg text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 active:scale-95 transition-all"
                          title="Ver foto del ticket"
                        >
                          <Camera className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <div className="text-right shrink-0">
                        <div className={`font-mono font-black text-sm ${item.type === "INCOME" ? "text-emerald-400" : "text-slate-100"}`}>
                          {item.type === "INCOME" ? "+" : "-"}{item.amount.toFixed(2)} €
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
      {/* Modal Visor de Comprobante / Ticket */}
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
