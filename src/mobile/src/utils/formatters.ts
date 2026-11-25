export const getLocalDateString = (d: Date = new Date()): string => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export const getLocalMonthString = (d: Date = new Date()): string => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
};

export const formatDateDisplay = (isoDate?: string | null): string => {
  if (!isoDate || !isoDate.trim()) return "N/A";
  const datePart = isoDate.trim().split("T")[0];
  const parts = datePart.split("-");
  if (parts.length !== 3) return isoDate;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
};

export const formatEuro = (val: number): string => {
  const num = Number.isFinite(val) ? val : 0;
  return `${num.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} €`;
};

export const parseDecimalInput = (raw: string): number => {
  if (!raw) return 0;
  const normalized = raw.replace(",", ".").trim();
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const triggerHaptic = (pattern: number | number[] = 20): void => {
  if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
    try {
      navigator.vibrate(pattern);
    } catch {
      // Ignorar si el navegador bloquea vibración sin gesto previo
    }
  }
};

export const normalizeServerUrl = (rawUrl: string): string => {
  let clean = (rawUrl || "").trim().replace(/\/+$/, "");
  if (clean && !/^https?:\/\//i.test(clean)) {
    clean = "http://" + clean;
  }
  return clean;
};

export const isNativeOrLocalOrigin = (origin: string): boolean => {
  if (!origin) return true;
  return (
    origin.includes("localhost") ||
    origin.includes("127.0.0.1") ||
    origin.startsWith("capacitor://") ||
    origin.startsWith("ionic://") ||
    origin.startsWith("file://")
  );
};
