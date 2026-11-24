import { useState, ChangeEvent } from "react";
import { Server, KeyRound, Check, X, RefreshCw, AlertTriangle, ShieldCheck, Zap } from "lucide-react";
import { testServerConnection, TestConnectionResult, pairWithPin } from "../services/api";

interface ServerConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentServerUrl: string;
  currentPairingToken: string;
  isOnline: boolean;
  isPaired: boolean;
  onSave: (newServerUrl: string, newPairingToken: string) => void;
}

export const ServerConfigModal = ({
  isOpen,
  onClose,
  currentServerUrl,
  currentPairingToken,
  isOnline,
  isPaired,
  onSave,
}: ServerConfigModalProps) => {
  const [serverUrl, setServerUrl] = useState(currentServerUrl || "");
  const [pairingToken, setPairingToken] = useState(currentPairingToken || "");
  const [pin, setPin] = useState("");
  const [isPairingPin, setIsPairingPin] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);

  if (!isOpen) return null;

  const handlePairPin = async () => {
    if (!pin.trim() || pin.trim().length !== 6) {
      setTestResult({
        success: false,
        isPaired: false,
        message: "Introduce el código PIN de 6 dígitos que ves en tu PC.",
      });
      return;
    }
    setIsPairingPin(true);
    setTestResult(null);
    try {
      const res = await pairWithPin(serverUrl, pin);
      if (res.success && res.pairingToken) {
        setPairingToken(res.pairingToken);
        setTestResult({
          success: true,
          isPaired: true,
          message: res.message,
        });
        onSave(serverUrl.trim(), res.pairingToken.trim());
      } else {
        setTestResult({
          success: false,
          isPaired: false,
          message: res.message,
        });
      }
    } finally {
      setIsPairingPin(false);
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const res = await testServerConnection(serverUrl, pairingToken);
      setTestResult(res);
    } catch {
      setTestResult({
        success: false,
        isPaired: false,
        message: "Error inesperado al probar la conexión",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = () => {
    onSave(serverUrl.trim(), pairingToken.trim());
    onClose();
  };

  const handleResetToOrigin = () => {
    if (typeof window !== "undefined" && window.location.origin) {
      setServerUrl(window.location.origin);
      setTestResult(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-5 max-w-sm w-full shadow-2xl flex flex-col gap-4 text-slate-100">
        {/* Cabecera del modal */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-extrabold text-sm text-slate-100">Conexión con el Servidor</h3>
              <p className="text-[10px] text-slate-400">Configura la IP del PC y tu token</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-xl text-slate-400 hover:text-slate-200 active:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Estado actual de conexión */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-2xl p-3 flex items-center justify-between text-xs">
          <span className="text-slate-400">Estado actual:</span>
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                isOnline
                  ? isPaired
                    ? "bg-emerald-400 shadow-sm shadow-emerald-400/50"
                    : "bg-amber-400 shadow-sm shadow-amber-400/50"
                  : "bg-rose-400"
              }`}
            />
            <span className="font-bold text-[11px]">
              {isOnline ? (isPaired ? "Conectado y Enlazado" : "Servidor Online (Sin Enlazar)") : "Desconectado (Offline)"}
            </span>
          </div>
        </div>

        {/* Campo: Dirección del Servidor */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-bold text-slate-300">Dirección URL / IP del PC</label>
            <button
              type="button"
              onClick={handleResetToOrigin}
              className="text-[10px] text-emerald-400 hover:underline"
            >
              Usar origen actual
            </button>
          </div>
          <div className="relative flex items-center">
            <Server className="w-4 h-4 text-slate-500 absolute left-3 pointer-events-none" />
            <input
              type="text"
              value={serverUrl}
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                setServerUrl(e.target.value);
                setTestResult(null);
              }}
              placeholder="http://192.168.1.45:8000"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500"
            />
          </div>
          <p className="text-[10px] text-slate-500">
            Ej: <code className="text-slate-400">http://192.168.1.45:8000</code> o la IP de tu Zona Wi-Fi.
          </p>
        </div>

        {/* Bloque: Emparejamiento por PIN (Recomendado sin cámara) */}
        <div className="bg-slate-950/80 border border-blue-500/40 rounded-2xl p-3 flex flex-col gap-2 shadow-inner">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-extrabold text-blue-300 flex items-center gap-1.5">
              <KeyRound className="w-3.5 h-3.5 text-blue-400" />
              <span>Vincular con PIN (Sin Cámara)</span>
            </label>
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
              Recomendado
            </span>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={pin}
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                setPin(e.target.value.replace(/\D/g, ""));
                setTestResult(null);
              }}
              placeholder="Ej: 582914"
              className="flex-1 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-center text-sm font-mono tracking-widest font-bold text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-400"
            />
            <button
              type="button"
              disabled={isPairingPin || pin.length !== 6}
              onClick={handlePairPin}
              className="px-3 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 active:scale-95 disabled:opacity-50 text-white font-bold text-xs flex items-center gap-1 transition-all"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>{isPairingPin ? "..." : "Vincular"}</span>
            </button>
          </div>
          <p className="text-[9.5px] text-slate-400">
            Mira el código generado en tu PC (<strong>Ajustes &gt; Companion Móvil</strong>).
          </p>
        </div>

        {/* Campo: Token de Emparejamiento */}
        <div className="flex flex-col gap-1.5">
          <label className="text-[11px] font-bold text-slate-300">Token de Emparejamiento</label>
          <div className="relative flex items-center">
            <KeyRound className="w-4 h-4 text-slate-500 absolute left-3 pointer-events-none" />
            <input
              type="text"
              value={pairingToken}
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                setPairingToken(e.target.value);
                setTestResult(null);
              }}
              placeholder="sec_..."
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500"
            />
          </div>
        </div>

        {/* Resultado del test */}
        {testResult && (
          <div
            className={`p-2.5 rounded-xl border text-xs flex items-center gap-2 ${
              testResult.success
                ? testResult.isPaired
                  ? "bg-emerald-950/40 border-emerald-500/40 text-emerald-300"
                  : "bg-amber-950/40 border-amber-500/40 text-amber-300"
                : "bg-rose-950/40 border-rose-500/40 text-rose-300"
            }`}
          >
            {testResult.success ? (
              testResult.isPaired ? (
                <ShieldCheck className="w-4 h-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
              )
            ) : (
              <X className="w-4 h-4 shrink-0 text-rose-400" />
            )}
            <span className="text-[11px] font-medium leading-tight">{testResult.message}</span>
          </div>
        )}

        {/* Botones de acción */}
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={handleTest}
            disabled={isTesting || !serverUrl.trim()}
            className="flex-1 py-2.5 px-3 rounded-xl font-bold text-xs bg-slate-800 hover:bg-slate-700 active:bg-slate-800 text-slate-200 border border-slate-700 flex items-center justify-center gap-1.5 disabled:opacity-50 transition-colors"
          >
            {isTesting ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-emerald-400" />
            ) : (
              <Check className="w-3.5 h-3.5" />
            )}
            <span>Probar</span>
          </button>

          <button
            type="button"
            onClick={handleSave}
            className="flex-1 py-2.5 px-3 rounded-xl font-extrabold text-xs bg-emerald-500 hover:bg-emerald-400 active:bg-emerald-600 text-slate-950 shadow-lg shadow-emerald-500/20 flex items-center justify-center gap-1.5 transition-colors"
          >
            <span>Guardar y Aplicar</span>
          </button>
        </div>
      </div>
    </div>
  );
};
