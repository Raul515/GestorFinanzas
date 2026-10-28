"""
Servicio agéntico de orquestación para el Copiloto Patrimonial (Spec 004 - Fase 3).
Implementa el bucle de Function Calling con Google Gemini (2.5 Pro / 3.1 Flash),
ejecutando herramientas bajo demanda, garantizando el veto a renta variable si el
fondo de emergencia no cubre 3 meses, exigiendo la doble tesis y degradando elegantemente.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, cast
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from backend.database.interfaz.db_interface import IRepository
from backend.services.copilot_tools import (
    COPILOT_TOOL_DEFINITIONS,
    execute_copilot_tool,
)

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_COPILOT_MODEL = "gemini-3.5-flash-lite"

SYSTEM_INSTRUCTION = """
Eres el 'Copiloto Patrimonial', un asistente sénior de inteligencia financiera y asesoría patrimonial integrado en la aplicación de gestión de finanzas personales.
Tu misión es guiar al usuario en la distribución de su presupuesto 50/30/20, asignación prudente de sus excedentes de caja ('Sin Asignar') y análisis de oportunidades de inversión, con máximo rigor técnico, empatía y pedagogía.

REGLAS DE PRIVACIDAD Y HERRAMIENTAS (PRIVACIDAD POR DISEÑO - PRINCIPIO 10):
1. NO conoces a priori los datos contables ni personales del usuario.
2. ÚNICAMENTE debes invocar herramientas si el usuario te lo solicita explícitamente o si su pregunta requiere inspeccionar sus finanzas para poder ser contestada con veracidad:
   - `get_financial_profile`: Invócala cuando el usuario consulte sobre su balance personal, ingresos, distribución 50/30/20, saldo 'Sin Asignar', fondo de emergencia o si tiene margen para invertir.
   - `get_watchlist_items`: Invócala cuando el usuario pregunte por sus valores en seguimiento o su cartera vigilada.
   - `get_cached_deepdive`: Invócala cuando el usuario pregunte por el análisis fundamental o tesis de una acción concreta (ej. ITX.MC, AAPL). Lee de la caché SQLite local sin coste de IA repetida.
   - `get_cached_macro_overview`: Invócala cuando el usuario pregunte por tipos del BCE, inflación, prima de riesgo o situación macroeconómica.
   - `search_local_knowledge`: Invócala cuando el usuario mencione sus notas de inversión, resúmenes guardados o documentos propios.
3. Si la pregunta es conceptual o teórica (ej. "¿qué es un fondo indexado?", "¿cómo funciona el interés compuesto?"), responde de forma clara y directa SIN invocar herramientas innecesarias.

SALVAGUARDA DE SEGURIDAD PATRIMONIAL (REGLA CONSTITUCIONAL INNEGOCIABLE - PRINCIPIO 9):
- Si invocas `get_financial_profile` y el resultado indica que `risk_investment_allowed` es False (el fondo de emergencia no cubre los 3 meses mínimos requeridos de gastos esenciales):
  - Tienes VETO TOTAL Y ABSOLUTO para recomendar, sugerir o validar compras de activos con riesgo o volatilidad (acciones individuales, renta variable, criptomonedas o fondos volátiles).
  - Tu recomendación DEBE SER IMPERATIVA Y PRIORITARIA: orientar cualquier excedente al Fondo de Emergencia hasta alcanzar la cobertura mínima de 3 meses.
  - Si el usuario pregunta dónde colocar ese dinero seguro mientras lo acumula, sugiere únicamente instrumentos sin riesgo de pérdida de capital ni volatilidad de cotización (cuentas remuneradas a la vista o depósitos a plazo fijo respaldados por el Fondo de Garantía de Depósitos).
  - Explica la lógica patrimonial: asumir volatilidad sin colchón de seguridad obliga a liquidar activos con pérdidas ante cualquier contingencia.

PRINCIPIO DE LA DOBLE TESIS OBLIGATORIA:
- Cuando analices o el usuario consulte sobre una empresa o activo de inversión:
  - Aunque la compañía sea excelente o tenga alta puntuación, NUNCA muestres un sesgo puramente alcista o de confirmación.
  - DEBES presentar obligatoriamente una DOBLE TESIS:
    1. Tesis favorable (fortalezas, retornos sobre capital ROIC/ROE, foso defensivo o valoración).
    2. OBLIGATORIAMENTE un mínimo de 2 riesgos bajistas cuantitativos o cualitativos respondiendo a: "¿Qué puede salir mal y cuánto beneficio o capital destruiría?".

ESTILO Y DESCARGO LEGAL:
- Redacta en español, con tono profesional, estructurado, claro y analítico, usando formato Markdown limpio.
- Incluye al final un breve descargo legal recordando que tus respuestas tienen carácter exclusivamente formativo y pedagógico, no constituyendo asesoramiento financiero regulado.
"""


def get_configured_copilot_model() -> str:
    """Resuelve el modelo Gemini configurado respetando la jerarquía de variables de entorno."""
    return (
        os.getenv("GEMINI_COPILOT_MODEL")
        or os.getenv("GEMINI_DEEPDIVE_MODEL")
        or os.getenv("GEMINI_MODEL")
        or DEFAULT_COPILOT_MODEL
    )


def run_copilot_turn(
    user_message: str,
    conversation_history: List[Dict[str, Any]],
    repo: IRepository,
    db: Optional[Session] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    knowledge_dir: Optional[str] = None,
    max_tool_iterations: int = 5,
) -> Dict[str, Any]:
    """
    Ejecuta un turno completo de conversación con el Copiloto Patrimonial.
    Orquesta el envío de historial, detección de Function Calls, ejecución local de tools y síntesis final.
    """
    effective_api_key = api_key or os.getenv("GEMINI_API_KEY")
    effective_model = model_name or get_configured_copilot_model()

    # Degradación elegante si no hay API key configurada
    if not effective_api_key:
        logger.info("Sin GEMINI_API_KEY detectada; devolviendo mensaje de degradación elegante.")
        return {
            "reply_text": (
                "🤖 **Copiloto Patrimonial (Modo Sin Conexión)**\n\n"
                "No se ha detectado una clave de API de Google Gemini (`GEMINI_API_KEY`).\n\n"
                "Para interactuar con el asistente inteligente y permitirle razonar sobre tu perfil financiero, "
                "debes añadir tu clave en el archivo `.env` del proyecto:\n"
                "```bash\n"
                "GEMINI_API_KEY=tu_api_key_aqui\n"
                "```\n"
                "*Tus datos contables permanecen 100% en tu máquina local en SQLite.*"
            ),
            "tools_used": [],
            "tool_calls_details": [],
            "model_used": "none",
            "error": False,
        }

    tools_used: List[str] = []
    tool_calls_details: List[Dict[str, Any]] = []

    try:
        client = genai.Client(api_key=effective_api_key)

        # Preparar declaraciones de herramientas para Function Calling
        function_declarations = [
            types.FunctionDeclaration(
                name=str(tool_def.get("name", "")),
                description=str(tool_def.get("description", "")),
                parameters=cast(Any, tool_def.get("parameters")),
            )
            for tool_def in COPILOT_TOOL_DEFINITIONS
        ]
        tool_config = types.Tool(function_declarations=function_declarations)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
            tools=[tool_config],
        )

        # Construir historial de contenidos para la API
        contents: List[types.Content] = []

        for msg in conversation_history:
            role = msg.get("role")
            content_text = msg.get("content", "")
            if not content_text:
                continue

            if role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content_text)],
                    )
                )
            elif role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=content_text)],
                    )
                )

        # Añadir mensaje actual del usuario
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_message)],
            )
        )

        # Bucle de Function Calling (máximo max_tool_iterations rondas)
        iterations = 0
        final_text = ""
        while iterations < max_tool_iterations:
            iterations += 1
            response = client.models.generate_content(
                model=effective_model,
                contents=contents,
                config=config,
            )

            # Si el modelo solicita llamadas a funciones
            if response.function_calls:
                # Añadir la respuesta del modelo con las function_calls al contexto
                if response.candidates and response.candidates[0].content:
                    contents.append(response.candidates[0].content)

                for call in response.function_calls:
                    call_name = call.name or ""
                    if not call_name:
                        continue

                    call_args = call.args if call.args is not None else {}
                    if not isinstance(call_args, dict):
                        try:
                            call_args = dict(call_args)
                        except Exception:
                            call_args = {}

                    logger.info("Copiloto invocó herramienta '%s' con argumentos: %s", call_name, call_args)

                    if call_name not in tools_used:
                        tools_used.append(call_name)

                    tool_result = execute_copilot_tool(
                        tool_name=call_name,
                        args=call_args,
                        repo=repo,
                        db=db,
                        knowledge_dir=knowledge_dir,
                    )

                    tool_calls_details.append(
                        {
                            "tool": call_name,
                            "args": call_args,
                            "result_summary": list(tool_result.keys()) if isinstance(tool_result, dict) else str(type(tool_result)),
                        }
                    )

                    # Enviar el resultado de vuelta al modelo como Part de function_response
                    response_part = types.Part.from_function_response(
                        name=call_name,
                        response={"result": tool_result},
                    )
                    contents.append(types.Content(role="user", parts=[response_part]))

            else:
                # No hay más llamadas a herramientas; el modelo generó la respuesta textual final
                final_text = response.text or ""
                return {
                    "reply_text": final_text,
                    "tools_used": tools_used,
                    "tool_calls_details": tool_calls_details,
                    "model_used": effective_model,
                    "error": False,
                }

        # Si agotó las iteraciones del bucle de herramientas
        return {
            "reply_text": final_text or "He recopilado los datos solicitados para tu consulta.",
            "tools_used": tools_used,
            "tool_calls_details": tool_calls_details,
            "model_used": effective_model,
            "error": False,
        }

    except Exception as exc:
        logger.error("Error durante la interacción con el modelo del Copiloto: %s", exc, exc_info=True)
        return {
            "reply_text": (
                "⚠️ **Aviso del Copiloto Patrimonial**\n\n"
                f"Ocurrió una incidencia técnica al comunicarse con el modelo de inteligencia artificial: {exc}.\n\n"
                "Por favor, comprueba tu conexión a internet o verifica los límites de uso de tu clave de Google Gemini."
            ),
            "tools_used": tools_used,
            "tool_calls_details": tool_calls_details,
            "model_used": effective_model,
            "error": True,
        }
