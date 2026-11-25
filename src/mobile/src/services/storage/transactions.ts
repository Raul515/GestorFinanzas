import { MobileTransaction } from "../../types";
import { STORAGE_KEYS } from "./config";

export const loadStoredTransactions = (): MobileTransaction[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.TRANSACTIONS);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
};

export const saveStoredTransactions = (txs: MobileTransaction[]): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(txs));
  } catch (err) {
    console.warn("Cuota de almacenamiento excedida, intentando purgar imágenes sincronizadas:", err);
    try {
      let cleaned = false;
      const stripped = txs.map((t) => {
        if (t.status === "SYNCED" && t.receipt_base64) {
          cleaned = true;
          return { ...t, receipt_base64: undefined };
        }
        return t;
      });
      if (cleaned) {
        localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(stripped));
        return;
      }
      const fullyStripped = txs.map((t) => ({ ...t, receipt_base64: undefined }));
      localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(fullyStripped));
    } catch (retryErr) {
      console.error("Fallo crítico al guardar en localStorage tras purgar comprobantes:", retryErr);
    }
  }
};

export const deleteStoredTransaction = (eventId: string): MobileTransaction[] => {
  const current = loadStoredTransactions();
  const updated = current.filter((t) => t.event_id !== eventId);
  saveStoredTransactions(updated);
  return updated;
};

export const loadStoredPendingDeletes = (): string[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.PENDING_DELETES);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch {
    return [];
  }
};

export const saveStoredPendingDeletes = (ids: string[]): void => {
  try {
    localStorage.setItem(STORAGE_KEYS.PENDING_DELETES, JSON.stringify(ids));
  } catch (err) {
    console.error("Error guardando borrados pendientes:", err);
  }
};

export const addPendingDelete = (idOrEventId: string | number): void => {
  const strId = String(idOrEventId).trim();
  const current = loadStoredPendingDeletes();
  if (!current.includes(strId)) {
    saveStoredPendingDeletes([...current, strId]);
  }
};

export const removePendingDelete = (idOrEventId: string | number): void => {
  const strId = String(idOrEventId).trim();
  const current = loadStoredPendingDeletes();
  saveStoredPendingDeletes(current.filter((id) => id !== strId));
};
