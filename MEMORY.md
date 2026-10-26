# MEMORY.md — Estado del Proyecto y Memoria Arquitectónica

## 1. Visión General del Proyecto y Estado Actual

- **Aplicación**: Gestor de Finanzas Personales Automatizado.
- **Metodología Central**: Presupuesto 50/30/20 (50% Necesidades Básicas, 30% Deseos, 20% Ahorro e Inversión) con seguimiento dinámico del fondo "Sin Asignar".
- **Arquitectura**:
  - **Backend**: FastAPI con SQLAlchemy 2.0 (mapeo declarativo fuertemente tipado) y esquemas Pydantic v2.
  - **Base de Datos**: SQLite local almacenada en `src/backend/data/finanzas.db` (excluida del control de versiones).
  - **Frontend**: Streamlit + Altair para gráficos interactivos. Consume el backend mediante `src/frontend/api_client.py`.
  - **Infraestructura**: Entorno Docker Compose local (`docker_local/`).
  - **Entorno de Ejecución**: El entorno virtual oficial de Python es `venv` (Python 3.11).

---

## 2. Metodología y Gobernanza (Spec-Driven Development)

- **Modo**: SDD anclado a especificaciones (*Spec-Anchored*).
- **Constitución**: [docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md) define los 12 principios innegociables.
- **Directrices de Agentes**: Definidas en [AGENTS.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/AGENTS.md).
- **Directorio de Especificaciones**: Las especificaciones activas residen en `specs/`.

---

## 3. Registro de Decisiones Clave

| Fecha | Decisión | Justificación |
| :--- | :--- | :--- |
| **2026-10-23** | Adopción de SDD Anclado a Specs | Garantizar cero alucinaciones, estricta separación entre lógica de negocio y presentación, y verificación previa rigurosa antes de implementar código. |
| **2026-10-23** | Estandarización en `venv` | Configurado en `pyrightconfig.json`, `.vscode/settings.json` y `README.md`. |
| **2026-10-23** | Salvaguarda de Seguridad (3 Meses de Reserva) | Prohibido recomendar o asignar capital a instrumentos de riesgo si el fondo de emergencia no cubre al menos 3 meses de gastos fijos esenciales. |
| **2026-10-23** | Descomposición en Especificaciones (000 a 005) | Secuencia aprobada: 000-Cimientos/SafetyGuard, 001-Radar, 002-Screener, 003-DeepDive, 004-Copiloto, 005-LangGraph. |
| **2026-10-23** | Selección de LLM: Google Gemini Pro | API de Gemini Pro seleccionada utilizando la API Key personal del usuario. Constitución adaptada para permitir la API manteniendo todos los datos contables en local. |
| **2026-10-23** | Entidad de Fondo de Emergencia y Meta Dinámica | Entidad SQLite con ajuste dinámico de objetivo ante incrementos en el gasto de Necesidades Básicas. |
| **2026-10-23** | Implementación y Verificación de Spec 000 | Suite inicial de pytest (23 pruebas pasando), desacoplamiento de cálculos financieros al backend, entidad y CRUD SQLite para fondo de emergencia, servicio de salvaguarda y endpoints REST. |
| **2026-10-23** | Spec 001 Fase 1 Completada | Instalación de dependencias externas (`yfinance`, `google-genai`, `feedparser`) y creación del modelo de caché de mercado con persistencia de 24h en SQLite (26/26 tests pasando). |
| **2026-10-23** | Spec 001 Fase 2 Completada | Creación del servicio de datos macroeconómicos con extracción de IBEX 35, EuroStoxx 50, S&P 500, Nasdaq 100, Bono US 10A vía `yfinance`, y rendimientos de Bono Español y Bund Alemán 10A vía API SDMX del BCE. Cálculo de la Prima de Riesgo en puntos básicos (34/34 tests pasando). |
| **2026-10-23** | Estándar Internacional de Lenguaje (Opción 1) y Seguridad Pre-Commit | Constitución y AGENTS.md actualizados a la Opción 1: backend, base de datos, modelos SQLAlchemy, esquemas Pydantic y endpoints de API 100% en inglés. Documentación, interfaz de usuario (Streamlit) y comunicación 100% en español. Carpetas de skills `.agents/` y `.claude/` excluidas explícitamente. Protocolo pre-commit obligatorio con `git status -u` y verificación activa de `.gitignore`. |
| **2026-10-26** | Spec 001 Fase 3 Completada | Agregador de noticias financieras públicas (Yahoo Finance `^IBEX` y feeds RSS de España/Eurozona: elEconomista, Cinco Días, BCE) y analizador de impacto y síntesis neutral mediante Google Gemini (`google-genai`). Soporte seguro de `.env` vía `python-dotenv` registrado en `.gitignore`. Degradación elegante ante ausencia de clave o fallo de cuota. Suite ampliada a 48/48 tests pasando. |
| **2026-10-26** | Regla de Implementación Estrictamente Fase a Fase | Gobernanza SDD actualizada en Constitución y AGENTS.md: toda spec debe implementarse fase a fase requiriendo confirmación y autorización explícita del usuario tras cada fase completada antes de iniciar la siguiente. Prohibido ejecutar múltiples fases de golpe. |

---

## 4. Deuda Técnica y Estado de las Especificaciones

1. **Spec 000 Completada**: Infraestructura de pruebas automatizadas y servicios financieros desacoplados.
2. **Hito Activo - Spec 001**: Radar Macroeconómico y Noticias (Fases 1, 2 y 3 completadas; 48 pruebas pasando).
3. **Fases Pendientes de Spec 001**:
   - Fase 4: Endpoints REST `/market/*` (`/macro-indicators`, `/news`, `/refresh`) con caché SQLite de 24h.
   - Fase 5: Pestaña en Streamlit "🌐 Radar Macro y Noticias" con sparklines Altair y filtros de impacto/temática.
   - Fase 6: Validación global, pruebas de regresión y verificación de arranque limpio.
4. **Especificaciones Posteriores**: Spec 002 (Screener), Spec 003 (Deep Dive contable), Spec 004 (Copiloto Patrimonial), Spec 005 (LangGraph).
