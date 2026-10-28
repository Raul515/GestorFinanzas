"""
Nodo de Análisis Fundamental y Calidad (Spec 005 - components/nodes).
Audita estados contables a 4 años, Piotroski F-Score (0-9) y formula la tesis favorable (Bull Case).
"""

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.database.interfaz.db_interface import IRepository
from backend.domain.states.investment_committee_state import InvestmentCommitteeState
from backend.components.tools.committee_tools import fetch_fundamental_deepdive
from backend.components.prompts.committee_prompts import SYSTEM_PROMPT_FUNDAMENTAL_ANALYST

load_dotenv()
logger = logging.getLogger(__name__)


def fundamental_analysis_node(
    state: InvestmentCommitteeState,
    repo: Optional[IRepository] = None,
    client: Optional[genai.Client] = None,
) -> Dict[str, Any]:
    """
    Realiza la auditoría cuantitativa contable y formula la tesis favorable bajo metodología Quality Value.
    Si el veto constitucional está activo, cortocircuita la ejecución.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    if state.get("veto_active", False):
        logger.info("FundamentalAnalysisNode: Omitido debido a veto constitucional activo.")
        return {
            "agent_logs": [
                {
                    "agent": "FundamentalAnalysisNode",
                    "timestamp": now_iso,
                    "message": "Auditoría fundamental omitida por veto constitucional activo.",
                    "data_keys": [],
                }
            ]
        }

    ticker = state.get("ticker")
    if not ticker:
        msg = "Consulta patrimonial general: no se especificó un ticker concreto para auditoría contable individual."
        return {
            "bull_thesis": msg,
            "agent_logs": [
                {
                    "agent": "FundamentalAnalysisNode",
                    "timestamp": now_iso,
                    "message": msg,
                    "data_keys": ["bull_thesis"],
                }
            ],
        }

    clean_ticker = ticker.strip().upper()

    # 1. Extracción de datos contables deterministas (Piotroski, FCF, solvencia)
    fund_data = state.get("fundamental_data")
    if not fund_data:
        fund_data = fetch_fundamental_deepdive(clean_ticker, repo=repo)

    if not fund_data:
        msg = f"No se pudieron extraer estados financieros cuantitativos para '{clean_ticker}'."
        return {
            "bull_thesis": msg,
            "agent_logs": [
                {
                    "agent": "FundamentalAnalysisNode",
                    "timestamp": now_iso,
                    "message": msg,
                    "data_keys": ["bull_thesis"],
                }
            ],
        }

    piotroski_score = fund_data.get("piotroski_score", {}).get("score", 0)
    company_name = fund_data.get("company_name", clean_ticker)
    fcf_yield = fund_data.get("fcf_analysis", {}).get("fcf_yield_percentage", 0.0)

    # 2. Generación cognitiva de la tesis favorable con Google Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    bull_thesis = ""

    if api_key or client is not None:
        try:
            genai_client = client or genai.Client(api_key=api_key)
            model_name = os.getenv("GEMINI_COMMITTEE_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"

            prompt_user = (
                f"Analiza la siguiente información contable cuantitativa de '{company_name}' ({clean_ticker}) "
                f"y redacta la Tesis Favorable (Bull Case):\n"
                f"- Piotroski F-Score: {piotroski_score}/9 puntos.\n"
                f"- FCF Yield: {fcf_yield:.2f}%.\n"
                f"- Resumen contable: {json.dumps(fund_data.get('fcf_analysis', {}), ensure_ascii=False)}\n"
                f"Destaca sus ventajas competitivas, capacidad de generación de caja y solvencia."
            )

            response = genai_client.models.generate_content(
                model=model_name,
                contents=prompt_user,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT_FUNDAMENTAL_ANALYST,
                    temperature=0.3,
                ),
            )
            bull_thesis = response.text or ""
        except Exception as exc:
            logger.warning("Error en llamada a Gemini en FundamentalAnalysisNode: %s. Aplicando fallback determinista.", exc)

    # Fallback determinista si no hay API key o falló la conexión
    if not bull_thesis:
        bull_thesis = (
            f"**Tesis Favorable (Quality Value)** para {company_name} ({clean_ticker}):\n"
            f"- **Piotroski F-Score**: {piotroski_score}/9 puntos, reflejando solidez contable.\n"
            f"- **Generación de Caja Libre**: FCF Yield del {fcf_yield:.2f}%.\n"
            f"- **Capacidad Operativa**: Estructura de capital consolidada y retornos sostenibles sobre la inversión."
        )

    log_msg = f"Auditoría contable completada para {clean_ticker}: Piotroski {piotroski_score}/9. Tesis favorable formulada."
    logger.info("FundamentalAnalysisNode: %s", log_msg)

    return {
        "fundamental_data": fund_data,
        "bull_thesis": bull_thesis,
        "agent_logs": [
            {
                "agent": "FundamentalAnalysisNode",
                "timestamp": now_iso,
                "message": log_msg,
                "data_keys": ["fundamental_data", "bull_thesis"],
            }
        ],
    }
