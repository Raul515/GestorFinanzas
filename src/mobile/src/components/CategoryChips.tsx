import { useState, ChangeEvent } from "react";
import { Search, X, Check, Plus } from "lucide-react";
import { SubcategoryItem } from "../types";

interface CategoryChipsProps {
  subcategories: SubcategoryItem[];
  selectedSubcategoryId: number | null;
  onSelectSubcategory: (subcat: SubcategoryItem) => void;
  onCreateSubcategory?: (name: string, categoryName: string) => Promise<SubcategoryItem | null> | SubcategoryItem | null;
}

export const getSubcategoryEmoji = (name: string): string => {
  const lower = name.toLowerCase();
  if (lower.includes("nómina") || lower.includes("nomina") || lower.includes("salario") || lower.includes("sueldo")) return "💰";
  if (lower.includes("bizum")) return "📲";
  if (lower.includes("devoluc") || lower.includes("reembols")) return "🔄";
  if (lower.includes("venta") || lower.includes("vinted") || lower.includes("wallapop")) return "🏷️";
  if (lower.includes("ingreso") || lower.includes("interes") || lower.includes("dividend")) return "💵";
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

export const CategoryChips = ({
  subcategories,
  selectedSubcategoryId,
  onSelectSubcategory,
  onCreateSubcategory,
}: CategoryChipsProps) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [newSubcatName, setNewSubcatName] = useState("");
  const [newCategoryName, setNewCategoryName] = useState("Deseos (30%)");

  const frequentSubcategories = subcategories.filter((s) => s.is_frequent);
  const activeSubcategories = frequentSubcategories.length > 0 ? frequentSubcategories : subcategories.slice(0, 6);

  const filteredModalList = subcategories.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.category_name.toLowerCase().includes(q);
  });

  const handleOpenCreateForm = () => {
    setNewSubcatName(searchQuery.trim());
    setIsCreating(true);
  };

  const handleSubmitNewSubcategory = async () => {
    if (!newSubcatName.trim()) return;

    if (onCreateSubcategory) {
      const created = await onCreateSubcategory(newSubcatName.trim(), newCategoryName);
      if (created) {
        onSelectSubcategory(created);
      }
    } else {
      // Fallback local con ID temporal
      const tempSubcat: SubcategoryItem = {
        id: -Date.now(),
        name: newSubcatName.trim(),
        category_id: newCategoryName.includes("50%") ? 2 : 3,
        category_name: newCategoryName,
        is_frequent: true,
      };
      onSelectSubcategory(tempSubcat);
    }

    setIsCreating(false);
    setSearchQuery("");
    setModalOpen(false);
  };

  return (
    <div className="w-full">
      {/* Carrusel horizontal de chips frecuentes */}
      <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5 px-0.5">
        {activeSubcategories.map((subcat) => {
          const isSelected = selectedSubcategoryId === subcat.id;
          const emoji = getSubcategoryEmoji(subcat.name);
          return (
            <button
              key={subcat.id}
              type="button"
              onClick={() => onSelectSubcategory(subcat)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all border shrink-0 active:scale-95 ${
                isSelected
                  ? "bg-emerald-500/18 text-emerald-300 border-emerald-500/60 shadow-[0_0_12px_rgba(16,185,129,0.25)] ring-1 ring-emerald-500/40"
                  : "bg-[#0F172A] text-slate-300 border-white/[0.08] hover:border-slate-700 active:bg-[#172033]"
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
          onClick={() => {
            setIsCreating(false);
            setModalOpen(true);
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap border border-white/[0.08] bg-[#0F172A] text-slate-400 hover:text-slate-200 shrink-0 active:scale-95 active:bg-[#172033]"
        >
          <Search className="w-3.5 h-3.5 text-slate-400" />
          <span>Ver todas</span>
        </button>
      </div>

      {/* Modal / Selector completo de subcategorías */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex flex-col justify-end sm:justify-center p-0 sm:p-4 animate-in fade-in duration-150">
          <div className="bg-[#0B1324] border border-white/[0.08] rounded-t-3xl sm:rounded-2xl max-h-[85vh] flex flex-col w-full max-w-md mx-auto shadow-2xl overflow-hidden">
            {/* Cabecera del modal */}
            <div className="flex items-center justify-between p-4 border-b border-white/[0.08]">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <Search className="w-4 h-4" />
                </div>
                <h3 className="font-extrabold text-slate-100 text-sm">
                  {isCreating ? "Nueva Subcategoría" : "Seleccionar Categoría"}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  setModalOpen(false);
                  setIsCreating(false);
                }}
                className="p-1 rounded-full text-slate-400 hover:text-slate-200 active:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {isCreating ? (
              /* Mini-formulario de alta rápida al vuelo */
              <div className="p-4 flex flex-col gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-slate-400">Nombre de la subcategoría</label>
                  <input
                    type="text"
                    value={newSubcatName}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setNewSubcatName(e.target.value)}
                    placeholder="Ej. Pádel, Sushi, Spotify..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                    autoFocus
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-slate-400">Tipo (Regla 50/30/20 o Ingreso)</label>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setNewCategoryName("Necesidades Básicas (50%)")}
                      className={`p-2 rounded-xl text-xs font-medium border text-center transition-all ${
                        newCategoryName.includes("50%")
                          ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 font-bold"
                          : "bg-slate-950 border-slate-800 text-slate-400"
                      }`}
                    >
                      🛒 Necesidad
                    </button>
                    <button
                      type="button"
                      onClick={() => setNewCategoryName("Deseos (30%)")}
                      className={`p-2 rounded-xl text-xs font-medium border text-center transition-all ${
                        newCategoryName.includes("30%")
                          ? "bg-amber-500/20 border-amber-500 text-amber-300 font-bold"
                          : "bg-slate-950 border-slate-800 text-slate-400"
                      }`}
                    >
                      ☕ Deseo
                    </button>
                    <button
                      type="button"
                      onClick={() => setNewCategoryName("Ingresos Netos")}
                      className={`p-2 rounded-xl text-xs font-medium border text-center transition-all ${
                        newCategoryName.includes("Ingreso")
                          ? "bg-sky-500/20 border-sky-500 text-sky-300 font-bold"
                          : "bg-slate-950 border-slate-800 text-slate-400"
                      }`}
                    >
                      💰 Ingreso
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsCreating(false)}
                    className="flex-1 py-2.5 rounded-xl bg-slate-800 text-slate-300 text-sm font-semibold active:bg-slate-700"
                  >
                    Atrás
                  </button>
                  <button
                    type="button"
                    onClick={handleSubmitNewSubcategory}
                    disabled={!newSubcatName.trim()}
                    className="flex-1 py-2.5 rounded-xl bg-emerald-500 text-slate-950 text-sm font-bold active:bg-emerald-400 disabled:opacity-50"
                  >
                    Crear y Usar
                  </button>
                </div>
              </div>
            ) : (
              /* Vista normal de búsqueda */
              <>
                {/* Input de búsqueda */}
                <div className="p-3 border-b border-slate-800 flex items-center gap-2">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
                    placeholder="Buscar (ej. gasolina, cena, súper)..."
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={handleOpenCreateForm}
                    className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 active:scale-95 shrink-0"
                    title="Nueva subcategoría"
                  >
                    <Plus className="w-5 h-5" />
                  </button>
                </div>

                {/* Lista con scroll */}
                <div className="overflow-y-auto p-3 flex flex-col gap-1.5 divide-y divide-slate-850">
                  {filteredModalList.length === 0 ? (
                    <div className="py-6 flex flex-col items-center justify-center gap-3 text-center">
                      <span className="text-slate-500 text-sm">
                        No se encontró "{searchQuery}".
                      </span>
                      <button
                        type="button"
                        onClick={handleOpenCreateForm}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-xs font-bold active:scale-95"
                      >
                        <Plus className="w-4 h-4" />
                        <span>Crear "{searchQuery || "Nueva"}"</span>
                      </button>
                    </div>
                  ) : (
                    <>
                      {filteredModalList.map((subcat) => {
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
                      })}

                      {/* Botón al final de la lista para crear otra */}
                      <button
                        type="button"
                        onClick={handleOpenCreateForm}
                        className="flex items-center justify-center gap-2 p-3 mt-2 rounded-xl border border-dashed border-slate-800 text-slate-400 hover:text-emerald-400 text-xs font-semibold"
                      >
                        <Plus className="w-4 h-4" />
                        <span>Añadir otra subcategoría al vuelo</span>
                      </button>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
