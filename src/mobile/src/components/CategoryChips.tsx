import React, { useState } from "react";
import { Search, X, Check } from "lucide-react";
import { SubcategoryItem } from "../types";

interface CategoryChipsProps {
  subcategories: SubcategoryItem[];
  selectedSubcategoryId: number | null;
  onSelectSubcategory: (subcat: SubcategoryItem) => void;
}

export const getSubcategoryEmoji = (name: string): string => {
  const lower = name.toLowerCase();
  if (lower.includes("café") || lower.includes("cafe") || lower.includes("desayun")) return "☕";
  if (lower.includes("super") || lower.includes("compra") || lower.includes("mercadona") || lower.includes("aliment")) return "🛒";
  if (lower.includes("restauran") || lower.includes("cen") || lower.includes("comid") || lower.includes("bar")) return "🍽️";
  if (lower.includes("gasol") || lower.includes("combust") || lower.includes("diesel")) return "⛽";
  if (lower.includes("farmac") || lower.includes("medic") || lower.includes("salud")) return "💊";
  if (lower.includes("transpor") || lower.includes("metro") || lower.includes("bus") || lower.includes("tren")) return "🚇";
  if (lower.includes("pádel") || lower.includes("padel") || lower.includes("gimnas") || lower.includes("deport")) return "🎾";
  if (lower.includes("alquiler") || lower.includes("hipoteca") || lower.includes("hogar") || lower.includes("vivienda")) return "🏠";
  if (lower.includes("luz") || lower.includes("agua") || lower.includes("gas") || lower.includes("suministr")) return "💡";
  if (lower.includes("suscrip") || lower.includes("netflix") || lower.includes("spotify") || lower.includes("internet")) return "📱";
  if (lower.includes("ropa") || lower.includes("calzad")) return "👕";
  if (lower.includes("viaj") || lower.includes("hotel") || lower.includes("vuelo")) return "✈️";
  if (lower.includes("emergenc") || lower.includes("colch")) return "🛡️";
  if (lower.includes("ahorr") || lower.includes("invers")) return "📈";
  return "🏷️";
};

export const CategoryChips: React.FC<CategoryChipsProps> = ({
  subcategories,
  selectedSubcategoryId,
  onSelectSubcategory,
}) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const frequentSubcategories = subcategories.filter((s) => s.is_frequent);
  const activeSubcategories = frequentSubcategories.length > 0 ? frequentSubcategories : subcategories.slice(0, 6);

  const filteredModalList = subcategories.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.category_name.toLowerCase().includes(q);
  });

  return (
    <div className="w-full">
      {/* Carrusel horizontal de chips frecuentes */}
      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-1 px-1">
        {activeSubcategories.map((subcat) => {
          const isSelected = selectedSubcategoryId === subcat.id;
          const emoji = getSubcategoryEmoji(subcat.name);
          return (
            <button
              key={subcat.id}
              type="button"
              onClick={() => onSelectSubcategory(subcat)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all border shrink-0 active:scale-95 ${
                isSelected
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500 ring-1 ring-emerald-500/50 shadow-sm shadow-emerald-950"
                  : "bg-slate-900 text-slate-300 border-slate-800 active:bg-slate-800"
              }`}
            >
              <span className="text-sm">{emoji}</span>
              <span>{subcat.name}</span>
            </button>
          );
        })}

        {/* Botón para abrir modal de búsqueda completa */}
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold whitespace-nowrap border border-slate-800 bg-slate-900/60 text-slate-400 shrink-0 active:scale-95 active:bg-slate-800"
        >
          <Search className="w-3.5 h-3.5" />
          <span>Ver todas</span>
        </button>
      </div>

      {/* Modal / Selector completo de subcategorías */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex flex-col justify-end sm:justify-center p-0 sm:p-4 animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-800 rounded-t-3xl sm:rounded-2xl max-h-[85vh] flex flex-col w-full max-w-md mx-auto shadow-2xl overflow-hidden">
            {/* Cabecera del modal */}
            <div className="flex items-center justify-between p-4 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Search className="w-5 h-5 text-emerald-400" />
                <h3 className="font-bold text-slate-100 text-base">Seleccionar Categoría</h3>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-100 active:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Input de búsqueda */}
            <div className="p-3 border-b border-slate-800">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Buscar (ej. gasolina, cena, súper)..."
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                autoFocus
              />
            </div>

            {/* Lista con scroll */}
            <div className="overflow-y-auto p-3 flex flex-col gap-1.5 divide-y divide-slate-850">
              {filteredModalList.length === 0 ? (
                <div className="py-8 text-center text-slate-500 text-sm">
                  No se encontraron subcategorías coincidentes.
                </div>
              ) : (
                filteredModalList.map((subcat) => {
                  const isSelected = selectedSubcategoryId === subcat.id;
                  const emoji = getSubcategoryEmoji(subcat.name);
                  return (
                    <button
                      key={subcat.id}
                      type="button"
                      onClick={() => {
                        onSelectSubcategory(subcat);
                        setModalOpen(false);
                      }}
                      className={`flex items-center justify-between p-3 rounded-xl transition-all text-left ${
                        isSelected
                          ? "bg-emerald-500/15 text-emerald-300 font-semibold"
                          : "hover:bg-slate-800/60 active:bg-slate-800 text-slate-200"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xl">{emoji}</span>
                        <div>
                          <div className="text-sm font-medium">{subcat.name}</div>
                          <div className="text-xs text-slate-500">{subcat.category_name}</div>
                        </div>
                      </div>
                      {isSelected && <Check className="w-5 h-5 text-emerald-400 shrink-0" />}
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
