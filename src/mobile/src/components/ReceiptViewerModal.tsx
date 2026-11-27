import { MouseEvent, useEffect, useState } from "react";
import { X } from "lucide-react";
import { fetchReceiptBlobUrl } from "../services/api";

interface ReceiptViewerModalProps {
  imageUrl: string | null;
  onClose: () => void;
}

export const ReceiptViewerModal = ({ imageUrl, onClose }: ReceiptViewerModalProps) => {
  const [resolvedSrc, setResolvedSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!imageUrl) {
      setResolvedSrc(null);
      return;
    }
    if (imageUrl.startsWith("data:") || imageUrl.startsWith("blob:")) {
      setResolvedSrc(imageUrl);
      return;
    }

    let cancelled = false;
    let createdBlobUrl: string | null = null;
    setLoading(true);
    setResolvedSrc(null);

    fetchReceiptBlobUrl(imageUrl).then((blobUrl) => {
      if (cancelled) {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        return;
      }
      createdBlobUrl = blobUrl;
      setResolvedSrc(blobUrl);
      setLoading(false);
    });

    return () => {
      cancelled = true;
      if (createdBlobUrl) {
        URL.revokeObjectURL(createdBlobUrl);
      }
    };
  }, [imageUrl]);

  if (!imageUrl) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-950/90 backdrop-blur-md flex flex-col items-center justify-center p-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md flex justify-between items-center mb-3"
        onClick={(e: MouseEvent) => e.stopPropagation()}
      >
        <span className="text-sm font-semibold text-slate-200">📸 Foto de Ticket / Comprobante</span>
        <button
          onClick={onClose}
          className="p-2 bg-slate-800 hover:bg-slate-700 rounded-full text-slate-300"
          aria-label="Cerrar vista de ticket"
        >
          <X className="w-5 h-5" />
        </button>
      </div>
      <div
        className="w-full max-w-md max-h-[80vh] min-h-[160px] overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 flex items-center justify-center"
        onClick={(e: MouseEvent) => e.stopPropagation()}
      >
        {loading ? (
          <span className="text-xs text-slate-400 py-10">Cargando comprobante...</span>
        ) : resolvedSrc ? (
          <img
            src={resolvedSrc}
            alt="Comprobante de ticket"
            className="max-w-full max-h-[78vh] object-contain"
          />
        ) : (
          <span className="text-xs text-rose-400 py-10">No se pudo cargar el comprobante.</span>
        )}
      </div>
    </div>
  );
};
