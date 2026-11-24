import { useState, useEffect, ChangeEvent, KeyboardEvent } from "react";
import { X, Plus, Trash2, RotateCcw, Check, Sparkles } from "lucide-react";
import { QuickPresetItem, SubcategoryItem } from "../types";
import { resetStoredQuickPresets, isIncomeSubcategory, findMatchingSubcategory } from "../services/storage";

interface ManagePresetsModalProps {
  isOpen: boolean;
  presets: QuickPresetItem[];
  subcategories: SubcategoryItem[];
  onClose: () => void;
  onSavePresets: (updated: QuickPresetItem[]) => void;
}

export const ManagePresetsModal = ({
  isOpen,
  presets,
  subcategories,
  onClose,
  onSavePresets,
}: ManagePresetsModalProps) => {
  const expenseSubcategories = subcategories.filter((s) => !isIncomeSubcategory(s));

  const [localPresets, setLocalPresets] = useState<QuickPresetItem[]>(presets);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Formulario de nuevo atajo
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmoji, setNewEmoji] = useState("⚡");
  const [newAmount, setNewAmount] = useState("");
  const [newSubcatName, setNewSubcatName] = useState(
    expenseSubcategories[0]?.name || "Café y Desayunos"
  );
  const [newConcept, setNewConcept] = useState("");

  useEffect(() => {
    if (isOpen) {
      setLocalPresets(presets);
      setEditingId(null);
      if (expenseSubcategories.length > 0 && !expenseSubcategories.some((s) => s.name === newSubcatName)) {
        setNewSubcatName(expenseSubcategories[0].name);
      }
    }
  }, [isOpen, presets]);

  if (!isOpen) return null;

  const handleUpdateAmount = (id: string, val: string) => {
    const num = parseFloat(val.replace(",", ".")) || 0;
    setLocalPresets((prev) =>
      prev.map((p) => (p.id === id ? { ...p, amount: Math.max(0, num) } : p))
    );
  };

  const handleUpdateName = (id: string, name: string) => {
    setLocalPresets((prev) =>
      prev.map((p) => (p.id === id ? { ...p, name } : p))
    );
  };

  const handleUpdateSubcategory = (id: string, subcatName: string) => {
    const foundSub = subcategories.find((s) => s.name === subcatName);
    setLocalPresets((prev) =>
      prev.map((p) =>
        p.id === id ? { ...p, subcategory_name: subcatName, subcategory_id: foundSub?.id } : p
      )
    );
  };

  const handleDelete = (id: string) => {
    setLocalPresets((prev) => prev.filter((p) => p.id !== id));
  };

  const handleResetDefaults = () => {
    const restored = resetStoredQuickPresets();
    setLocalPresets(restored);
  };

  const handleAddPreset = () => {
    const amt = parseFloat(newAmount.replace(",", ".")) || 0;
    if (!newName.trim() || amt <= 0) return;

    const newPreset: QuickPresetItem = {
      id: `preset-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      name: newName.trim(),
      emoji: newEmoji.trim() || "⚡",
      amount: Math.round(amt * 100) / 100,
      subcategory_name: newSubcatName,
      concept: newConcept.trim() || newName.trim(),
    };

    setLocalPresets((prev) => [...prev, newPreset]);
    setNewName("");
    setNewAmount("");
    setNewConcept("");
    setShowAddForm(false);
  };

  const handleSaveAndClose = () => {
    onSavePresets(localPresets);
    onClose();
  };

  return (
    <div className="fixed top-0 left-0 right-0 h-[var(--vvh,100dvh)] z-50 flex items-center justify-center p-3 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-sm flex flex-col max-h-[calc(var(--vvh,100dvh)*0.85)] shadow-2xl overflow-hidden">
        {/* Cabecera del modal */}
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400 font-bold text-base">⚙️ Atajos 1-Tap</span>
            <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono">
              {localPresets.length}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 active:bg-slate-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Contenido / Lista de Atajos */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5 no-scrollbar">
          {localPresets.map((preset) => {
            const isEditing = editingId === preset.id;
            return (
              <div
                key={preset.id}
                className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-2.5 flex flex-col gap-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-lg shrink-0">{preset.emoji}</span>
                    {isEditing ? (
                      <input
                        type="text"
                        value={preset.name}
                        onChange={(e: ChangeEvent<HTMLInputElement>) => handleUpdateName(preset.id, e.target.value)}
                        onBlur={() => setEditingId(null)}
                        onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
                          if (e.key === "Enter") setEditingId(null);
                        }}
                        autoFocus
                        className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-xs text-white font-bold flex-1 min-w-0 w-full"
                      />
                    ) : (
                      <div
                        onClick={() => setEditingId(preset.id)}
                        className="font-bold text-xs text-slate-200 truncate cursor-pointer hover:text-emerald-400"
                        title="Toca para editar el nombre"
                      >
                        {preset.name}
                      </div>
                    )}
                  </div>

                  {/* Input de Importe */}
                  <div className="flex items-center gap-1 shrink-0">
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      value={preset.amount}
                      onChange={(e: ChangeEvent<HTMLInputElement>) => handleUpdateAmount(preset.id, e.target.value)}
                      className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-emerald-400 font-mono font-bold text-right w-20"
                    />
                    <span className="text-xs text-slate-500 font-bold">€</span>
                  </div>

                  {/* Botón Borrar */}
                  <button
                    type="button"
                    onClick={() => handleDelete(preset.id)}
                    className="p-1 rounded text-slate-500 hover:text-rose-400 active:bg-slate-800"
                    title="Eliminar atajo"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Subcategoría asignada */}
                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-900">
                  {(() => {
                    const matchedSub = findMatchingSubcategory(preset, expenseSubcategories);
                    const activeSubName =
                      preset.subcategory_id && expenseSubcategories.some((s) => s.id === preset.subcategory_id)
                        ? expenseSubcategories.find((s) => s.id === preset.subcategory_id)?.name || preset.subcategory_name
                        : preset.subcategory_name && expenseSubcategories.some((s) => s.name === preset.subcategory_name)
                        ? preset.subcategory_name
                        : matchedSub?.name || expenseSubcategories[0]?.name || preset.subcategory_name;
                    return (
                      <>
                        <span className="truncate max-w-[150px]">
                          📂 {activeSubName}
                        </span>
                        <select
                          value={activeSubName}
                          onChange={(e: ChangeEvent<HTMLSelectElement>) => handleUpdateSubcategory(preset.id, e.target.value)}
                          className="bg-slate-900 text-[10px] text-slate-300 border border-slate-800 rounded px-1.5 py-0.5 max-w-[165px]"
                        >
                          {expenseSubcategories.map((s) => (
                            <option key={s.id} value={s.name}>
                              {s.name}
                            </option>
                          ))}
                        </select>
                      </>
                    );
                  })()}
                </div>
              </div>
            );
          })}

          {/* Formulario para añadir nuevo atajo */}
          {showAddForm ? (
            <div className="bg-slate-950 border border-emerald-500/40 rounded-xl p-3 flex flex-col gap-2 animate-fade-in">
              <div className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5" />
                <span>Nuevo Atajo 1-Tap</span>
              </div>
              <div className="grid grid-cols-4 gap-2">
                <input
                  type="text"
                  placeholder="Emoji"
                  value={newEmoji}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setNewEmoji(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg p-1.5 text-center text-sm"
                  maxLength={2}
                />
                <input
                  type="text"
                  placeholder="Nombre (ej. Pan)"
                  value={newName}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setNewName(e.target.value)}
                  className="col-span-3 bg-slate-900 border border-slate-700 rounded-lg p-1.5 text-xs text-white"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="relative">
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="Importe €"
                    value={newAmount}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setNewAmount(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg p-1.5 text-xs text-emerald-400 font-mono font-bold"
                  />
                  <span className="absolute right-2 top-1.5 text-xs text-slate-500">€</span>
                </div>
                <select
                  value={newSubcatName}
                  onChange={(e: ChangeEvent<HTMLSelectElement>) => setNewSubcatName(e.target.value)}
                  className="bg-slate-900 border border-slate-700 rounded-lg p-1.5 text-xs text-slate-300 truncate"
                >
                  {expenseSubcategories.map((s) => (
                    <option key={s.id} value={s.name}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="px-2.5 py-1 text-xs text-slate-400 hover:text-white"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={handleAddPreset}
                  disabled={!newName.trim() || !newAmount}
                  className="px-3 py-1 bg-emerald-500 text-slate-950 font-bold rounded-lg text-xs disabled:opacity-50"
                >
                  Añadir
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              className="w-full py-2 border border-dashed border-slate-800 rounded-xl text-xs font-semibold text-slate-400 hover:text-emerald-400 hover:border-emerald-500/40 flex items-center justify-center gap-1.5 transition-all"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Añadir nuevo atajo</span>
            </button>
          )}
        </div>

        {/* Pie del modal con acciones */}
        <div className="p-3 border-t border-slate-800 flex items-center justify-between gap-2 bg-slate-950/40">
          <button
            type="button"
            onClick={handleResetDefaults}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-slate-800 text-[11px] font-medium text-slate-400 hover:text-amber-400 active:scale-95"
            title="Restaurar Café (1,50€), Cena (20,00€), Cine (5,50€)"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Restaurar</span>
          </button>

          <button
            type="button"
            onClick={handleSaveAndClose}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl bg-emerald-500 text-slate-950 font-bold text-xs hover:bg-emerald-400 active:scale-95 shadow-md shadow-emerald-500/20"
          >
            <Check className="w-3.5 h-3.5 stroke-[3]" />
            <span>Guardar cambios</span>
          </button>
        </div>
      </div>
    </div>
  );
};
