import { Capacitor } from "@capacitor/core";
import { Directory, Encoding, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";
import { MobileTransaction } from "../types";

export const exportTransactionsToJsonFile = async (transactions: MobileTransaction[]): Promise<void> => {
  const pending = transactions.filter((t) => t.status === "PENDING_SYNC");
  const payload = {
    device_id: Capacitor.isNativePlatform() ? "mobile-apk" : "mobile-pwa",
    exported_at_utc: new Date().toISOString(),
    transactions: pending.map((t) => ({
      event_id: t.event_id,
      scope: t.scope,
      type: t.type || "EXPENSE",
      amount: t.amount,
      description: t.description,
      date: t.date,
      subcategory_id: t.subcategory_id,
      subcategory_name: t.subcategory_name,
      created_at_utc: t.created_at_utc,
    })),
  };

  const jsonStr = JSON.stringify(payload, null, 2);
  const filename = `evt_mob_${Date.now()}.json`;

  if (Capacitor.isNativePlatform()) {
    try {
      const savedFile = await Filesystem.writeFile({
        path: filename,
        data: jsonStr,
        directory: Directory.Cache,
        encoding: Encoding.UTF8,
      });
      await Share.share({
        title: "Exportación Gestor Finanzas",
        text: `Lote de ${pending.length} movimientos pendientes exportados.`,
        url: savedFile.uri,
        files: [savedFile.uri],
        dialogTitle: "Guardar o compartir JSON",
      });
      return;
    } catch (nativeErr: any) {
      if (nativeErr?.message && String(nativeErr.message).toLowerCase().includes("cancel")) {
        return;
      }
      console.warn("Fallo en exportación nativa Capacitor, usando fallback web:", nativeErr);
    }
  }

  if (typeof navigator !== "undefined" && navigator.share && navigator.canShare) {
    try {
      const file = new File([jsonStr], filename, { type: "application/json" });
      if (navigator.canShare({ files: [file] })) {
        await navigator.share({
          files: [file],
          title: "Exportación Gestor Finanzas",
          text: `Lote de ${pending.length} gastos pendientes exportados.`,
        });
        return;
      }
    } catch (err: any) {
      if (err && err.name === "AbortError") {
        return;
      }
      console.warn("Fallo al compartir archivo con navigator.share, usando fallback de descarga:", err);
    }
  }

  const blob = new Blob([jsonStr], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
