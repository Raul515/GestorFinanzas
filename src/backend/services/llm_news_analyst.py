import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai import types

from backend.domain.schemas.market import (
    AnalyzedNewsItem,
    ImpactLevel,
    MarketNewsResponse,
    NewsItem,
    NewsTopic,
)
from backend.services.news_service import fetch_financial_news

# Cargar automáticamente variables de entorno desde el archivo .env si existe
load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"

SYSTEM_INSTRUCTION = """
Eres un analista macroeconómico y financiero sénior, extremadamente riguroso, sobrio y objetivo.
Tu misión es evaluar noticias financieras públicas para un residente particular e inversor en España.
Tu análisis debe:
1. Eliminar cualquier sensacionalismo, dramatismo o 'clickbait'.
2. Evaluar el impacto real para un residente en España (teniendo en cuenta la política del BCE, Euríbor/hipotecas, IPC, empleo o empresas del IBEX 35).
3. Clasificar cada noticia en:
   - "impact": Estrictamente uno de ["Alto", "Medio", "Bajo"].
   - "topic": Estrictamente una de estas categorías:
     - "Política Monetaria BCE / Tipos e Hipotecas"
     - "Macroeconomía España y Eurozona"
     - "Resultados Empresariales"
     - "Geopolítica y Mercados Globales"
   - "summary": Síntesis neutral y fáctica en español de exactamente 1 o 2 frases.
Debes responder ÚNICAMENTE en formato JSON como un array de objetos con las claves: "id", "impact", "topic", "summary".
"""


def _get_gemini_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """Inicializa el cliente de Google GenAI si la clave de API está presente."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or not key.strip():
        return None
    clean_key = key.strip().strip("'\"")
    if not clean_key:
        return None
    try:
        return genai.Client(api_key=clean_key)
    except Exception as e:
        logger.warning(f"No se pudo inicializar genai.Client: {e}")
        return None


def _fallback_analyzed_items(
    news_items: List[NewsItem],
    reason_message: str,
) -> List[AnalyzedNewsItem]:
    """Genera una lista de noticias analizadas con valores neutros por defecto ante ausencia o fallo de IA."""
    fallback_list: List[AnalyzedNewsItem] = []
    for item in news_items:
        fallback_list.append(
            AnalyzedNewsItem(
                id=item.id,
                title=item.title,
                link=item.link,
                source=item.source,
                published_at=item.published_at,
                impact=ImpactLevel.MEDIUM.value,
                topic=NewsTopic.MACROECONOMY.value,
                summary=reason_message,
            )
        )
    return fallback_list


def analyze_news_batch(
    news_items: List[NewsItem],
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Tuple[List[AnalyzedNewsItem], bool]:
    """
    Analiza un lote de noticias financieras mediante la API de Google Gemini / Gemma.
    Retorna una tupla con (lista de noticias analizadas, ai_analysis_available).
    En caso de falta de clave o fallo de red/cuota, degrada elegantemente sin lanzar excepción.
    """
    if not news_items:
        return [], True

    client = _get_gemini_client(api_key=api_key)
    if not client:
        logger.info("GEMINI_API_KEY no configurada. Devolviendo noticias con degradación elegante.")
        fallback = _fallback_analyzed_items(
            news_items,
            reason_message="Análisis de IA no disponible (clave GEMINI_API_KEY no configurada en .env).",
        )
        return fallback, False

    raw_model = (
        model_name
        or os.getenv("GEMINI_NEWS_MODEL")
        or os.getenv("GEMINI_MODEL")
        or DEFAULT_GEMINI_MODEL
    )
    target_model = raw_model.strip().strip("'\"") or DEFAULT_GEMINI_MODEL

    # Construir contenido optimizado para el lote (RNF-3: economía de tokens)
    items_payload = [
        {"id": item.id, "title": item.title, "source": item.source}
        for item in news_items
    ]
    prompt_text = (
        "Analiza las siguientes noticias y devuelve un array JSON con su clasificación:\n"
        + json.dumps(items_payload, ensure_ascii=False, indent=2)
    )

    models_to_try = [target_model]
    if target_model != "gemma-4-26b-a4b-it" and "gemma" in target_model.lower():
        models_to_try.append("gemma-4-26b-a4b-it")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        temperature=0.2,
    )

    last_error = None
    parsed_results = None

    for m in models_to_try:
        try:
            response = client.models.generate_content(
                model=m,
                contents=prompt_text,
                config=config,
            )
            raw_text = response.text or "[]"
            parsed_results = json.loads(raw_text)
            if not isinstance(parsed_results, list):
                raise ValueError(f"La respuesta del modelo no es una lista JSON: {type(parsed_results)}")
            target_model = m
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Error durante el análisis de noticias con ({m}): {e}")

    if parsed_results is None:
        logger.warning(f"Todos los modelos de noticias fallaron. Último error: {last_error}")
        fallback = _fallback_analyzed_items(
            news_items,
            reason_message="Análisis de IA no disponible temporalmente (error al consultar Gemini/Gemma API).",
        )
        return fallback, False

    # Mapear los resultados por id
    results_by_id = {}
    for entry in parsed_results:
        if isinstance(entry, dict) and "id" in entry:
            results_by_id[str(entry["id"])] = entry

    valid_impacts = {i.value for i in ImpactLevel}
    valid_topics = {t.value for t in NewsTopic}

    analyzed_items: List[AnalyzedNewsItem] = []
    for item in news_items:
        analysis = results_by_id.get(item.id, {})
        impact = analysis.get("impact", ImpactLevel.MEDIUM.value)
        if impact not in valid_impacts:
            impact = ImpactLevel.MEDIUM.value

        topic = analysis.get("topic", NewsTopic.MACROECONOMY.value)
        if topic not in valid_topics:
            topic = NewsTopic.MACROECONOMY.value

        summary = analysis.get("summary") or item.title

        analyzed_items.append(
            AnalyzedNewsItem(
                id=item.id,
                title=item.title,
                link=item.link,
                source=item.source,
                published_at=item.published_at,
                impact=impact,
                topic=topic,
                summary=summary,
            )
        )

    return analyzed_items, True


def get_analyzed_market_news(
    limit: int = 15,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> MarketNewsResponse:
    """
    Función de orquestación que recupera noticias financieras públicas y aplica
    el análisis con IA, empaquetando el resultado en un esquema MarketNewsResponse.
    """
    raw_news = fetch_financial_news(limit=limit)
    analyzed_news, ai_available = analyze_news_batch(
        raw_news,
        api_key=api_key,
        model_name=model_name,
    )
    notes = "Noticias analizadas con Google Gemini" if ai_available else "Noticias en modo de degradación elegante (sin IA)"

    return MarketNewsResponse(
        news=analyzed_news,
        fetched_at=datetime.now(timezone.utc),
        is_cached=False,
        ai_analysis_available=ai_available,
        notes=notes,
    )
