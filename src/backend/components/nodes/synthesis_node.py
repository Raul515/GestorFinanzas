"""
Nodo de Síntesis y Veredicto Final del Comité (Spec 005 - components/nodes).
Presidente del Comité Asesor de Inversión y Planificador Patrimonial (Supervisor).
Emite el veredicto vinculante integrando la salvaguarda constitucional, la doble tesis y el plan de acción.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.components.prompts.committee_prompts import SYSTEM_PROMPT_PORTFOLIO_SYNTHESIZER

load_dotenv()
logger = logging.getLogger(__name__)


def synthesis_node(
    state: InvestmentCommitteeState,
    client: Optional[genai.Client] = None,
) -> Dict[str, Any]:
    """
    Integra la deliberación del Comité y formula el veredicto final y el plan de acción.
    Si el veto constitucional está activo, emite un dictamen vinculante de bloqueo patrimonial.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = state.get("ticker", "General")
    safety_status = state.get("safety_status", {})
    coverage_months = safety_status.get("coverage_months", 0.0)

    # 1. Verificación de Veto Constitucional (Principio 9)
    if state.get("veto_active", False):
        gap = safety_status.get(
            "gap_to_target",
            max(0.0, safety_status.get("target_3m", 0.0) - safety_status.get("current_balance", 0.0)),
        )
        unassigned = safety_status.get("unassigned_balance", 0.0)

        final_verdict = (
            f"⛔ VETO CONSTITUCIONAL ACTIVO (Principio 9 de la Constitución):\n"
            f"El Fondo de Emergencia cubre actualmente {coverage_months:.1f} meses de gastos fijos esenciales, "
            f"por debajo del umbral mínimo obligatorio de 3.0 meses. "
            f"Queda estrictamente prohibida cualquier asignación de capital a activos financieros de riesgo "
            f"(acciones, fondos indexados o renta variable)."
        )
        action_plan = (
            f"📋 Plan de Acción Inmediato de Blindaje Patrimonial:\n"
            f"1. Destinar el 100% del saldo no asignado disponible ({unassigned:,.2f} €) a la cuenta remunerada o depósito de reserva.\n"
            f"2. Brecha pendiente para alcanzar la cobertura de seguridad básica (3.0 meses): {gap:,.2f} €.\n"
            f"3. Una vez alcanzado el objetivo de 3.0 meses, el Comité desbloqueará el análisis y asignación en activos de inversión."
        )

        msg = f"Veredicto final emitido con VETO CONSTITUCIONAL ACTIVO ({coverage_months:.1f} meses de cobertura)."
        logger.warning("SynthesisNode: %s", msg)

        return {
            "final_verdict": final_verdict,
            "action_plan": action_plan,
            "agent_logs": [
                {
                    "agent": "SynthesisNode",
                    "timestamp": now_iso,
                    "message": msg,
                    "data_keys": ["final_verdict", "action_plan"],
                }
            ],
        }

    # 2. Veredicto cuando la salvaguarda está superada
    bull_thesis = state.get("bull_thesis") or "Tesis favorable basada en fundamentales cuantitativos sólidos."
    bear_risks = state.get("bear_risks") or []
    macro_data = state.get("macro_data") or {}
    unassigned = safety_status.get("unassigned_balance", 0.0)
    initial_notes = state.get("initial_notes") or ""

    api_key = os.getenv("GEMINI_API_KEY")
    final_verdict = ""
    action_plan = ""

    if api_key or client is not None:
        try:
            genai_client = client or genai.Client(api_key=api_key)
            model_name = os.getenv("GEMINI_COMMITTEE_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

            risks_formatted = "\n".join(f"- {r}" for r in bear_risks) if bear_risks else "- Sin riesgos particulares reportados."

            prompt_user = (
                f"Emite el veredicto final vinculante y el plan de acción estructurado para '{ticker}'.\n\n"
                f"--- CONTEXTO PATRIMONIAL DEL USUARIO ---\n"
                f"- Cobertura del Fondo de Emergencia: {coverage_months:.1f} meses (Supera el umbral constitucional de 3.0 meses).\n"
                f"- Saldo 'Sin Asignar' disponible para inversión: {unassigned:,.2f} €.\n"
                f"- Notas del usuario: {initial_notes}\n\n"
                f"--- DELIBERACIÓN DEL COMITÉ ASESOR ---\n"
                f"1. Tesis Favorable (Analista Fundamental):\n{bull_thesis}\n\n"
                f"2. Auditoría de Riesgos Bajistas (Red Team - Doble Tesis):\n{risks_formatted}\n\n"
                f"3. Entorno Macroeconómico:\n{macro_data}\n\n"
                f"INSTRUCCIONES:\n"
                f"Separa tu respuesta con dos encabezados claros:\n"
                f"### VEREDICTO FINAL\n(Conclusión clara y ponderada sopesando el Bull Case con los Bear Risks).\n\n"
                f"### PLAN DE ACCIÓN\n(Estrategia gradual de asignación prudente sobre el saldo disponible, margen de seguridad y tramos)."
            )

            response = genai_client.models.generate_content(
                model=model_name,
                contents=prompt_user,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_PORTFOLIO_SYNTHESIZER,
                    temperature=0.3,
                ),
            )
            raw_text = response.text or ""
            if "### PLAN DE ACCIÓN" in raw_text:
                parts = raw_text.split("### PLAN DE ACCIÓN")
                final_verdict = parts[0].replace("### VEREDICTO FINAL", "").strip()
                action_plan = parts[1].strip()
            elif "### VEREDICTO FINAL" in raw_text:
                final_verdict = raw_text.replace("### VEREDICTO FINAL", "").strip()
                action_plan = "Ejecutar asignación prudente en tramos conforme a la disponibilidad de liquidez."
            else:
                final_verdict = raw_text.strip()
                action_plan = "Ejecutar asignación prudente en tramos escalonados."
        except Exception as exc:
            logger.warning("Error en llamada a Gemini en SynthesisNode: %s. Utilizando síntesis de contingencia.", exc)

    # Contingencia determinista si Gemini no está configurado o falla
    if not final_verdict:
        final_verdict = (
            f"⚖️ VEREDICTO FINAL: APROBADO CON ASIGNACIÓN GRADUAL CONDICIONADA.\n"
            f"La salvaguarda patrimonial está garantizada con {coverage_months:.1f} meses de cobertura en el Fondo de Emergencia. "
            f"La tesis favorable sobre '{ticker}' se apoya en fundamentales cuantitativos y capacidad de generación de caja, "
            f"pero queda estrictamente supeditada al control de los {len(bear_risks)} riesgos bajistas identificados por el Comité. "
            f"Se autoriza la toma de posición con compras escalonadas y margen de seguridad."
        )

    if not action_plan:
        tramo_1 = unassigned * 0.3
        tramo_2 = unassigned * 0.3
        reserva = unassigned * 0.4
        action_plan = (
            f"📋 Plan de Acción de Asignación Prudente:\n"
            f"1. Tramo Inicial (30%): Posición piloto por importe estimado de {tramo_1:,.2f} €.\n"
            f"2. Tramo de Acumulación (30%): Reservar {tramo_2:,.2f} € para acumular si se manifiestan los riesgos bajistas identificados.\n"
            f"3. Colchón Estratégico (40% restante): Mantener {reserva:,.2f} € en liquidez para preservar opcionalidad.\n"
            f"4. Seguimiento: Revisión periódica en el próximo cierre mensual."
        )

    log_msg = f"Veredicto final emitido satisfactoriamente para '{ticker}' (Salvaguarda superada: {coverage_months:.1f} meses)."
    logger.info("SynthesisNode: %s", log_msg)

    return {
        "final_verdict": final_verdict,
        "action_plan": action_plan,
        "agent_logs": [
            {
                "agent": "SynthesisNode",
                "timestamp": now_iso,
                "message": log_msg,
                "data_keys": ["final_verdict", "action_plan"],
            }
        ],
    }
