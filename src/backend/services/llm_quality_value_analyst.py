"""
Servicio agéntico para la generación de tesis de inversión bajo metodología Quality Value (Spec 003 - Fase 3).
Utiliza Google Gemini (3.1 Flash / 2.5 Pro) para sintetizar cuadrantes, los 6 ingredientes, matriz de riesgos
y valoración proyectada a 5 años con TIR del 15% al 20%, degradando elegantemente si la API no está disponible.
"""

import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.domain.schemas.deepdive import DeepDiveResponse, QualityValueReport

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_DEEPDIVE_MODEL = "gemini-2.5-pro"

SYSTEM_INSTRUCTION = """
Eres un analista de inversión institucional sénior especializado en la metodología 'Quality Value'.
Tu análisis debe ser extremadamente riguroso, escéptico y centrado en la protección de capital.

METODOLOGÍA QUALITY VALUE:
1. Clasificación en uno de los 3 cuadrantes:
   - "Quality Value": Empresa de excelente calidad (altos retornos ROIC/ROE, foso defensivo duradero, fuerte conversión a caja) cotizando a un precio razonable o con descuento debido a un problema coyuntural o temporal.
   - "Calidad Cara": Empresa excelente pero con múltiplos muy exigentes que no ofrecen margen de seguridad ni potencial de TIR > 15%.
   - "Trampa de Valor": Empresa aparentemente barata por múltiplos pero con fundamentales deteriorados (pérdida de foso, quema de caja, apalancamiento creciente o disrupción tecnológica).

2. Evaluación de los 6 Ingredientes Clave:
   - "long_term_growth": Crecimiento secular a largo plazo.
   - "tailwinds": Vientos de cola estructurales del sector.
   - "market_leadership": Liderazgo y cuota de mercado.
   - "moat": Foso defensivo (efectos de red, costes de cambio, escala, patentes/marcas).
   - "high_returns_on_capital": Retornos sobre el capital invertido (ROIC y ROE).
   - "temporary_headwinds": Presencia de dificultades temporales que justifican el precio actual.

3. Modelo de Negocio y Matriz de Riesgos ("¿Qué puede salir mal?"):
   - Cómo genera ingresos y dinámica del capital circulante.
   - MÍNIMO 2 riesgos bajistas obligatorios y cuantitativos respondiendo a: "¿Qué puede salir mal y cuánto beneficio/caja destruiría?".

4. Valoración a 5 Años y Rentabilidad Exigida (TIR):
   - Proyección a 5 años comparando Escenario Base vs Escenario de Estrés.
   - Definición de la "target_irr_entry_zone": Rango de precio de entrada exigiendo una TIR anualizada del 15% al 20% con margen de seguridad.

REGLAS DE FORMATO:
Debes responder EXCLUSIVAMENTE con un objeto JSON válido con las siguientes claves:
{
  "quadrant": "Quality Value" | "Calidad Cara" | "Trampa de Valor",
  "summary_thesis": "string con la tesis ejecutiva concisa",
  "six_ingredients": {
    "long_term_growth": "...",
    "tailwinds": "...",
    "market_leadership": "...",
    "moat": "...",
    "high_returns_on_capital": "...",
    "temporary_headwinds": "..."
  },
  "business_model_and_risks": {
    "business_model": "...",
    "capital_dynamics": "..."
  },
  "bearish_risks": [
    "Riesgo bajista 1 con impacto cuantitativo estimado...",
    "Riesgo bajista 2 con impacto cuantitativo estimado..."
  ],
  "valuation_projections": {
    "scenario_base": { "target_price": 0.0, "exit_multiple": 0.0, "expected_irr": 0.0 },
    "scenario_stress": { "target_price": 0.0, "exit_multiple": 0.0, "expected_irr": 0.0 }
  },
  "target_irr_entry_zone": "Rango en divisa de cotización para alcanzar TIR 15%-20% (ej. 38.00 € - 42.00 €)"
}
"""


def _get_gemini_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """Inicializa el cliente de Google GenAI si la clave de API está configurada."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or not key.strip():
        return None
    clean_key = key.strip().strip("'\"")
    if not clean_key:
        return None
    try:
        return genai.Client(api_key=clean_key)
    except Exception as exc:
        logger.warning("Fallo al inicializar genai.Client: %s", exc)
        return None


def get_configured_deepdive_model(model_override: Optional[str] = None) -> str:
    """Resuelve el modelo Gemini a emplear priorizando GEMINI_DEEPDIVE_MODEL, GEMINI_MODEL y fallback por defecto."""
    if model_override and model_override.strip():
        return model_override.strip().strip("'\"")

    env_deepdive = os.getenv("GEMINI_DEEPDIVE_MODEL")
    if env_deepdive and env_deepdive.strip():
        return env_deepdive.strip().strip("'\"")

    env_general = os.getenv("GEMINI_MODEL")
    if env_general and env_general.strip():
        return env_general.strip().strip("'\"")

    return DEFAULT_DEEPDIVE_MODEL


def _build_accounting_payload(deepdive_data: DeepDiveResponse) -> Dict[str, Any]:
    """Construye el resumen fáctico de magnitudes contables extraídas en Python para enviar al LLM."""
    statements_summary = []
    for s in deepdive_data.statements:
        statements_summary.append(
            {
                "year": s.year,
                "revenue": s.revenue,
                "gross_profit": s.gross_profit,
                "operating_income": s.operating_income,
                "net_income": s.net_income,
                "diluted_eps": s.diluted_eps,
                "operating_cash_flow": s.operating_cash_flow,
                "capital_expenditure": s.capital_expenditure,
                "free_cash_flow": s.free_cash_flow,
                "total_debt": s.total_debt,
                "cash_and_equivalents": s.cash_and_equivalents,
            }
        )

    return {
        "ticker": deepdive_data.ticker,
        "name": deepdive_data.name,
        "sector": deepdive_data.sector,
        "industry": deepdive_data.industry,
        "country": deepdive_data.country,
        "currency": deepdive_data.currency,
        "current_price": deepdive_data.current_price,
        "market_cap": deepdive_data.market_cap,
        "valuation_multiples": {
            "pe_trailing": deepdive_data.pe_trailing,
            "pe_forward": deepdive_data.pe_forward,
            "ev_to_ebitda": deepdive_data.ev_to_ebitda,
            "price_to_book": deepdive_data.price_to_book,
            "dividend_yield": deepdive_data.dividend_yield,
            "beta": deepdive_data.beta,
        },
        "piotroski_score": {
            "total_score": deepdive_data.piotroski.total_score,
            "max_score": deepdive_data.piotroski.max_score,
            "rating": deepdive_data.piotroski.rating,
        },
        "fcf_metrics": deepdive_data.fcf_metrics,
        "historical_statements": statements_summary,
        "is_financial_institution": deepdive_data.is_financial_institution,
    }


def analyze_quality_value(
    deepdive_data: DeepDiveResponse,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[QualityValueReport]:
    """
    Sintetiza la tesis agéntica Quality Value utilizando la API de Google Gemini.
    Retorna una instancia validada de QualityValueReport o None si no hay clave o falla la llamada.
    """
    client = _get_gemini_client(api_key=api_key)
    if not client:
        logger.info(
            "GEMINI_API_KEY no configurada. Continuando con diagnóstico cuantitativo puro sin informe agéntico."
        )
        return None

    target_model = get_configured_deepdive_model(model_name)
    accounting_payload = _build_accounting_payload(deepdive_data)

    prompt_text = (
        "Analiza la siguiente empresa bajo la metodología Quality Value a partir de sus datos contables verificados:\n"
        + json.dumps(accounting_payload, ensure_ascii=False, indent=2)
    )

    try:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.2,
        )

        response = client.models.generate_content(
            model=target_model,
            contents=prompt_text,
            config=config,
        )

        raw_text = response.text or "{}"
        parsed_data = json.loads(raw_text)

        if not isinstance(parsed_data, dict):
            logger.warning(
                "La respuesta del modelo para %s no es un objeto JSON válido: %s",
                deepdive_data.ticker,
                type(parsed_data),
            )
            return None

        # Normalización defensiva del cuadrante
        raw_quadrant = str(parsed_data.get("quadrant", "")).strip()
        if "quality value" in raw_quadrant.lower():
            quadrant = "Quality Value"
        elif "cara" in raw_quadrant.lower():
            quadrant = "Calidad Cara"
        elif "trampa" in raw_quadrant.lower() or "trap" in raw_quadrant.lower():
            quadrant = "Trampa de Valor"
        else:
            quadrant = "Quality Value"

        # Asegurar un mínimo de 2 riesgos bajistas obligatorios
        bearish_risks = parsed_data.get("bearish_risks") or []
        if not isinstance(bearish_risks, list):
            bearish_risks = [str(bearish_risks)]
        if len(bearish_risks) < 2:
            bearish_risks.append("Riesgo de compresión de múltiplos ante endurecimiento monetario global.")

        report = QualityValueReport(
            quadrant=quadrant,
            summary_thesis=parsed_data.get("summary_thesis")
            or f"Diagnóstico de inversión para {deepdive_data.ticker}.",
            six_ingredients=parsed_data.get("six_ingredients") or {},
            business_model_and_risks=parsed_data.get("business_model_and_risks") or {},
            bearish_risks=bearish_risks,
            valuation_projections=parsed_data.get("valuation_projections") or {},
            target_irr_entry_zone=parsed_data.get("target_irr_entry_zone")
            or "Zona de entrada sujeta a revisión de múltiplos históricos.",
        )
        return report

    except Exception as exc:
        logger.warning(
            "Fallo en la llamada agéntica de Gemini para %s: %s",
            deepdive_data.ticker,
            exc,
        )
        return None
