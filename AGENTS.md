# AGENTS.md — Directrices Operativas para Agentes

Este repositorio sigue la metodología **Desarrollo Guiado por Especificaciones (Spec-Driven Development - SDD)** en **modo anclado a especificaciones**. Todos los agentes que trabajen en este código deben cumplir estrictamente las normas expuestas a continuación.

---

## 1. Ley Suprema: La Constitución

Antes de planificar, diseñar o escribir una sola línea de código, lee y cumple íntegramente:
👉 **[docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md)**

Si alguna tarea, instrucción o decisión entra en conflicto con la Constitución, **detente de inmediato** y consulta al usuario.

---

## 2. Flujo Anclado a Especificaciones (Spec-Anchored)

1. **Mandato de Especificaciones**:
   - Nada se implementa sin una especificación formalmente aprobada en el directorio `specs/`.
   - Si un caso borde, decisión técnica o fórmula contable no está definido en la especificación activa, **detente y pregunta** al usuario. Queda terminantemente prohibido hacer suposiciones sobre lógica financiera.
2. **Implementación Estrictamente Fase a Fase con Puerta de Confirmación**:
   - Toda especificación dividida en fases debe ejecutarse de forma estrictamente secuencial, **una sola fase a la vez**.
   - Al concluir cada fase y verificar que la totalidad de sus pruebas automatizadas pasan al 100%, el agente debe **detenerse obligatoriamente**, resumir los entregables completados y solicitar confirmación/autorización explícita al usuario antes de pasar a la siguiente fase.
   - Queda **terminantemente prohibido implementar múltiples fases de golpe** o encadenar fases consecutivas sin la validación previa del usuario.
3. **Arquitectura Desacoplada**:
   - Los algoritmos financieros (presupuesto 50/30/20, desviaciones, cálculos de fondos de seguridad e indicadores) y las herramientas de agentes deben implementarse como servicios o funciones puras testeables bajo `src/backend/services/`.
   - La interfaz de Streamlit (`src/frontend/`) es exclusivamente una capa de presentación visual.
4. **Veracidad Cuantitativa y Pruebas Obligatorias**:
   - Prohibido simular, alucinar o falsear métricas financieras en código de producción.
   - Toda lógica financiera y herramienta de agente requiere pruebas automatizadas con `pytest` pasando al 100% antes de considerar completada cualquier fase.
5. **Protección Patrimonial y Salvaguarda de Seguridad**:
   - **Regla innegociable**: Jamás sugerir, asignar o permitir inversiones con riesgo si el fondo de emergencia no cubre al menos 3 meses de gastos fijos esenciales.
6. **Seguridad Pre-Commit y Verificación de `.gitignore`**:
   - **Protocolo obligatorio antes de cada commit**:
     1. Ejecutar `git status -u` para inspeccionar la totalidad de archivos creados o modificados.
     2. Verificar activamente que ningún archivo nuevo o modificado contenga claves API, tokens, contraseñas, bases de datos locales (`finanzas.db`) o volcados de datos reales.
     3. Confirmar que los archivos temporales o sensibles queden debidamente registrados en `.gitignore` antes de ejecutar `git add` o `git commit`.
7. **Convenciones de Idioma y Nomenclatura (Opción 1 - Estándar Internacional)**:
   - **Código Backend, Base de Datos y API (100% en Inglés)**: Tablas, columnas, modelos SQLAlchemy, esquemas Pydantic, routers, endpoints, funciones y variables redactados en inglés (ej. `Category`, `Transaction`, `MonthlyBudget`, `EmergencyFund`, `MarketCache`, `amount`, `current_balance`, `/categories`, `/advisor/safety-status`).
   - **Interfaz de Usuario, Documentación y Explicaciones (100% en Español)**: Interfaz gráfica de Streamlit, documentación (`specs/`, `README.md`, guías), docstrings explicativos y comunicación en el chat en español.
   - **Commits en Git**: Estándar *Conventional Commits* con tipo y ámbito en inglés y descripción en español (`feat(scope): descripción en español`).
8. **Exclusión de Carpetas de Habilidades de Terceros**:
   - Las carpetas `.agents/` y `.claude/` contienen skills y configuraciones de agentes descargadas de terceros; quedan excluidas de cualquier refactorización, traducción o modificación de idioma.

---

## 3. Comandos Oficiales de Verificación y Ejecución

Verifica siempre los cambios utilizando el entorno virtual local oficial (`venv`):

- **Ejecutar Pruebas Automatizadas**:
  ```powershell
  .\venv\Scripts\pytest -v
  ```
- **Comprobación de Sintaxis Python**:
  ```powershell
  .\venv\Scripts\python -m compileall src tests
  ```
- **Iniciar Backend (FastAPI)**:
  ```powershell
  $env:PYTHONPATH="src"
  .\venv\Scripts\uvicorn backend.main:app --reload --port 8000
  ```
- **Iniciar Frontend (Streamlit)**:
  ```powershell
  .\venv\Scripts\streamlit run src/frontend/app.py
  ```
- **Docker Compose (Entorno Local Completo)**:
  ```powershell
  cd docker_local
  docker compose -f docker-compose.yml -f docker-compose.extend.yml up --build
  ```

---

## 4. Mantenimiento de la Memoria Persistente

Actualiza **[MEMORY.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/MEMORY.md)** siempre que:
- Se tome o refine una decisión arquitectónica o de nomenclatura.
- Se inicie o concluya una especificación o fase de desarrollo.
- Se identifiquen deudas técnicas o restricciones críticas del sistema.
