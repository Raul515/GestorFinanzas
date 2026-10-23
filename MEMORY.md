# MEMORY.md — Project State & Architectural Memory

## 1. Project Overview & Current State

- **Application**: Gestor de Finanzas Personales Automatizado.
- **Core Methodology**: 50/30/20 budget framework (Needs 50%, Wants 30%, Savings 20%) with dynamic unassigned funds tracking.
- **Architecture**:
  - **Backend**: FastAPI with SQLAlchemy 2.0 (typed declarative mapping) and Pydantic schemas.
  - **Database**: Local SQLite database located at `src/backend/data/finanzas.db` (git-ignored).
  - **Frontend**: Streamlit + Altair for interactive charts. Consumes backend via `src/frontend/api_client.py`.
  - **Infrastructure**: Local Docker Compose setup (`docker_local/`).
  - **Environment**: Official Python virtual environment is `venv` (Python 3.11).

---

## 2. Methodology & Governance (Spec-Driven Development)

- **Mode**: Spec-Anchored SDD.
- **Constitution**: [docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md) defines 7 non-negotiable principles.
- **Agent Guidelines**: Defined in [AGENTS.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/AGENTS.md).
- **Specs Directory**: Active specifications reside in `specs/`.

---

## 3. Log of Key Decisions

| Date | Decision | Rationale |
| :--- | :--- | :--- |
| **2026-10-23** | Adoption of Spec-Anchored SDD | Ensure zero hallucinations, strict separation between business logic and UI, and rigorous verification before writing code. |
| **2026-10-23** | Standardized on `venv` | Configured in `pyrightconfig.json`, `.vscode/settings.json`, and `README.md`. Redundant `.venv` identified for cleanup. |
| **2026-10-23** | Safety Guard Rule (3 Months Reserve) | Financial agents are forbidden from recommending risk-bearing assets until 3 months of essential fixed costs are secured. |
| **2026-10-23** | Language Policy | Code, schemas, and git commits in English; user interface, documentation, and explanations in Spanish. |
| **2026-10-23** | Spec 001 Defined: Market Radar & Fundamentals | Drafted specs/001-analisis-mercado/spec.md focusing strictly on WHAT & WHY using EARS notation. |
| **2026-10-23** | Spec Decomposition (000 to 005) | Approved sequence: 000-Cimientos/SafetyGuard, 001-Radar, 002-Screener, 003-DeepDive, 004-Copiloto, 005-LangGraph. Draft 001 to be superseded by 003. |
| **2026-10-23** | LLM Selection: Google Gemini Pro | Gemini Pro API chosen with user's API Key. Constitution amended (Principles 1 & 6) to permit Gemini API while keeping accounting data local. |
| **2026-10-23** | Emergency Fund Entity & Dynamic Target | Formal SQLite entity `EmergencyFund` agreed. Target adjusts dynamically when Needs increase, auto-reallocating monthly savings. |
| **2026-10-23** | Spec 000 Implemented & Tested | Completed: pytest suite (23 tests passing), financial_calculator decoupled to backend, EmergencyFund entity + CRUD in SQLite, SafetyGuard service + REST API (/advisor/*), and Streamlit integration. |
| **2026-10-23** | Spec 001 Phase 1 Completed | Installed yfinance, google-genai, feedparser. Created MarketCache entity in SQLite with 24h TTL and CRUD methods (26/26 tests passing). |
| **2026-10-23** | Spec 001 Phase 2 Completed | Implemented MacroIndicator & MacroOverviewResponse schemas, market_data service pulling IBEX 35, EuroStoxx 50, S&P 500, Nasdaq 100, US 10Y via yfinance, and Spanish/German 10Y yields via official ECB SDMX API. Calculated Spanish Risk Premium (pb) with 30-day sparklines. Unit tests created and verified (34/34 tests passing). |

---

## 4. Technical Debt & Planned Improvements

1. **Spec 000 Completed**: Testing infrastructure and decoupled financial services established.
2. **Current Milestone - Spec 001**: Radar Macro & Noticias (Fases 1 y 2 completadas; 34 tests pasando).
3. **Spec 001 Pending Phases**:
   - Fase 3: Agregación de noticias RSS/Yahoo y análisis con Gemini Pro.
   - Fase 4: Endpoints REST `/market/*`.
   - Fase 5: UI Streamlit con pestaña "🌐 Radar Macro y Noticias".
   - Fase 6: Validación global y pruebas de regresión.
4. **Subsequent Specs**: Spec 002 (Screener), Spec 003 (Deep Dive contable), Spec 004 (Copiloto Patrimonial), Spec 005 (LangGraph).
