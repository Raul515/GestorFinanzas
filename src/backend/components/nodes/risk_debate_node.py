"""
Nodo de Auditoría de Riesgos y Debate (Spec 005 - components/nodes).
Agente 'Red Team': desafía la tesis favorable y formula obligatoriamente al menos 2 riesgos bajistas severos.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.components.prompts.committee_prompts import SYSTEM_PROMPT_RISK_DEBATER

load_dotenv()
logger = logging.getLogger(__name__)


def risk_debate_node(
    state: InvestmentCommitteeState,
    client: Optional[genai.Client] = None,
) -> Dict[str, Any]:
    """
    Formula la doble tesis de inversión obligatoria identificando al menos 2 riesgos bajistas severos.
    Si el veto constitucional está activo, cortocircuita la ejecución.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    if state.get("veto_active", False):
        logger.info("RiskDebateNode: Omitido debido a veto constitucional activo.")
        return {
            "agent_logs": [
                {
                    "agent": "RiskDebateNode",
                    "timestamp": now_iso,
                    "message": "Auditoría de riesgos omitida por veto constitucional activo.",
                    "data_keys": [],
                }
            ]
        }

    ticker = state.get("ticker", "General")
    bull_thesis = state.get("bull_thesis", "")
    fundamental_data = state.get("fundamental_data", {})
    macro_data = state.get("macro_data", {})

    api_key = os.getenv("GEMINI_API_KEY")
    bear_risks: List[str] = []

    if api_key or client is not None:
        try:
            genai_client = client or genai.Client(api_key=api_key)
            model_name = os.getenv("GEMINI_COMMITTEE_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

            prompt_user = (
                f"Audita críticamente la oportunidad sobre '{ticker}'.\n"
                f"Tesis favorable recibida:\n{bull_thesis}\n\n"
                f"Datos contables y de caja:\n{fundamental_data}\n\n"
                f"Entorno macroeconómico:\n{macro_data}\n\n"
                f"Responde a: '¿Qué puede salir mal y cuánto beneficio destruiría?'.\n"
                f"Formula obligatoriamente al menos 2 riesgos bajistas severos, separando cada riesgo en una línea que empiece por '- ' o un número."
            )

            response = genai_client.models.generate_content(
                model=model_name,
                contents=prompt_user,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_RISK_DEBATER,
                    temperature=0.3,
                ),
            )
            raw_text = response.text or ""
            for line in raw_text.split("\n"):
                clean = line.strip()
                if (clean.startswith("- ") or clean.startswith("* ") or (len(clean) > 2 and clean[0].isdigit() and clean[1] in (".", ")"))) and len(clean) > 10:
                    risk_content = clean.lstrip("-*0123456789.) ").strip()
                    if risk_content:
                        bear_risks.append(risk_content)
        except Exception as exc:
            logger.warning("Error en llamada a Gemini en RiskDebateNode: %s. Aplicando riesgos cuantitativos predefinidos.", exc)

    # Garantía Constitucional: Obligatoriedad de al menos 2 riesgos bajistas
    if len(bear_risks) < 2:
        if ticker and ticker != "General":
            bear_risks = [
                f"Compresión de márgenes operativos por inflación en costes o presión competitiva en {ticker}.",
                f"Sensibilidad a tipos de interés del BCE y desaceleración del consumo en los principales mercados de {ticker}.",
            ]
        else:
            bear_risks = [
                "Riesgo de asignación de capital excesiva a instrumentos volátiles sin suficiente margen de seguridad.",
                "Riesgo de tipos de interés restrictivos que reduzcan las valoraciones globales de los activos financieros.",
            ]

    log_msg = f"Auditoría de riesgos completada para {ticker}: {len(bear_risks)} riesgos bajistas severos identificados."
    logger.info("RiskDebateNode: %s", log_msg)

    return {
        "bear_risks": bear_risks,
        "agent_logs": [
            {
                "agent": "RiskDebateNode",
                "timestamp": now_iso,
                "message": log_msg,
                "data_keys": ["bear_risks"],
            }
        ],
    }
