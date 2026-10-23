# Constitution: Gestor de Finanzas Personales

1. **Local Stack**: FastAPI, SQLite local, Streamlit y Docker; LLM cloud permitido vía Google Gemini API (clave de usuario).
2. **Spec Mandate**: Nada se implementa fuera de la spec activa; ante cualquier duda o vacío, parar y preguntar.
3. **Decoupled Logic & SSOT**: Lógica 50/30/20 y herramientas desacopladas como módulos puros de la UI de Streamlit. Fuente única de verdad para cualquier cálculo financiero (cero duplicación en frontend).
4. **SOLID Architecture**: Código estructurado bajo principios SOLID: responsabilidad única por módulo, inversión de dependencias mediante interfaces (`db_interface.py`) y segregación de repositorios.
5. **KISS & YAGNI**: Simplicidad sobre complejidad. Prohibido añadir abstracciones prematuras o capas innecesarias no requeridas por la especificación.
6. **Veracity & Testing**: Prohibido alucinar métricas financieras; tests automáticos pasan al 100% o no hay avance.
7. **Type Safety & Defensive Validation**: Tipado estricto con Pydantic v2 en todas las fronteras de datos y precisión numérica garantizada.
8. **Graceful Degradation**: Caídas de servicios externos (Yahoo, BCE, Gemini) deben gestionarse de forma resiliente mediante fallbacks o cachés, sin romper la aplicación.
9. **Safety Guard**: Prohibido recomendar activos de riesgo sin 3 meses de gastos fijos cubiertos en fondo de emergencia.
10. **Local Privacy**: Datos contables detallados residen en local; a Gemini API solo se envían datos de mercado o resúmenes autorizados.
11. **Language & Git Policy**: Código y schemas en inglés; commits semánticos atómicos con tipo en inglés y descripción en español (`feat(scope): descripción en español`); UI de Streamlit, documentación y explicaciones en español.
