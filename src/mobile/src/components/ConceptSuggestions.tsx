import React from "react";
import { Tag } from "lucide-react";

interface ConceptSuggestionsProps {
  concept: string;
  onChangeConcept: (val: string) => void;
  frequentConcepts: string[];
}

export const ConceptSuggestions: React.FC<ConceptSuggestionsProps> = ({
  concept,
  onChangeConcept,
  frequentConcepts,
}) => {
  const suggestions = frequentConcepts.slice(0, 6);

  return (
    <div className="w-full flex flex-col gap-1.5">
      <div className="relative flex items-center">
        <Tag className="w-4 h-4 text-slate-500 absolute left-3 pointer-events-none" />
        <input
          type="text"
          value={concept}
          onChange={(e) => onChangeConcept(e.target.value)}
          placeholder="Concepto (ej. Café con tostada)..."
          maxLength={100}
          className="w-full bg-slate-900 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
        />
      </div>

      {suggestions.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5 px-0.5">
          {suggestions.map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onChangeConcept(item)}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-900/80 hover:bg-slate-850 active:bg-slate-800 border border-slate-800 text-slate-400 whitespace-nowrap shrink-0 active:scale-95 transition-all"
            >
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
