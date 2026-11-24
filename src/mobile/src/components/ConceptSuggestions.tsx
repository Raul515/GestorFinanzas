import { ChangeEvent } from "react";
import { Tag } from "lucide-react";

interface ConceptSuggestionsProps {
  concept: string;
  onChangeConcept: (val: string) => void;
  frequentConcepts: string[];
}

export const ConceptSuggestions = ({
  concept,
  onChangeConcept,
  frequentConcepts,
}: ConceptSuggestionsProps) => {
  const suggestions = frequentConcepts.slice(0, 6);

  return (
    <div className="w-full flex flex-col gap-1.5">
      <div className="relative flex items-center">
        <Tag className="w-4 h-4 text-slate-500 absolute left-3 pointer-events-none" />
        <input
          type="text"
          value={concept}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onChangeConcept(e.target.value)}
          placeholder="Concepto (ej. Desayuno, Supermercado)..."
          maxLength={100}
          className="w-full bg-[#0F172A] border border-white/[0.08] rounded-xl pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30 transition-all shadow-sm"
        />
      </div>

      {suggestions.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5 px-0.5">
          {suggestions.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onChangeConcept(item)}
              className="text-[10.5px] px-2.5 py-1 rounded-lg bg-[#0F172A] hover:bg-[#172033] active:bg-[#1A263D] border border-white/[0.06] text-slate-400 hover:text-slate-200 whitespace-nowrap shrink-0 active:scale-95 transition-all"
            >
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
