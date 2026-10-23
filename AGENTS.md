# AGENTS.md — Agent Operating Guidelines

This repository follows **Spec-Driven Development (SDD)** in **spec-anchored mode**. All agents working on this codebase must strictly adhere to the rules outlined below.

---

## 1. Supreme Law: The Constitution

Before performing any planning, design, or coding, read and comply with:
👉 **[docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md)**

If any task or instruction conflicts with the Constitution, **stop immediately** and consult the user.

---

## 2. Spec-Anchored Workflow

1. **Spec Mandate**:
   - Nothing is implemented without an approved specification in the `specs/` directory.
   - If an edge case, architecture decision, or calculation detail is undefined in the active spec, **stop and ask** the user. Never make assumptions on financial logic.
2. **Decoupled Architecture**:
   - Financial algorithms (50/30/20 budgeting, deviation calculations, investment logic) and agent tools must be implemented as testable, decoupled functions or services (under `src/backend/` or domain modules).
   - The Streamlit interface (`src/frontend/`) is purely a presentation layer consuming APIs/services.
3. **Quantitative Veracity & Tests**:
   - Never hallucinate, mock, or fake financial metrics in production code.
   - Automated tests are required for all financial calculation modules and agent tools before merging or marking work as complete.
4. **User Protection & Privacy**:
   - Accounting and financial transaction data must remain local.
   - **Non-negotiable rule**: Never suggest or allocate to risk-bearing investment assets if the safety fund does not cover at least 3 months of essential fixed expenses.
5. **Language & Git Conventions**:
   - **English**: Code, variable names, functions, classes, and Pydantic/SQLAlchemy schemas.
   - **Conventional Commits**: Commit type/scope in English with description in Spanish (`feat(scope): descripción en español`).
   - **Spanish**: User interface (Streamlit), user-facing explanations, documentation, and chat communication.

---

## 3. Verification & Execution Commands

Always verify changes using the official local virtual environment (`venv`):

- **Run Automated Tests**:
  ```powershell
  .\venv\Scripts\pytest
  ```
- **Static Type Checking & Linting**:
  ```powershell
  .\venv\Scripts\python -m pyright
  ```
- **Run Backend (FastAPI)**:
  ```powershell
  $env:PYTHONPATH="src"
  .\venv\Scripts\uvicorn backend.main:app --reload --port 8000
  ```
- **Run Frontend (Streamlit)**:
  ```powershell
  .\venv\Scripts\streamlit run src/frontend/app.py
  ```
- **Docker Compose (Full Local Stack)**:
  ```powershell
  cd docker_local
  docker compose -f docker-compose.yml -f docker-compose.extend.yml up --build
  ```

---

## 4. Persistent Memory Maintenance

Update **[MEMORY.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/MEMORY.md)** whenever:
- An architectural decision is finalized.
- A new spec or milestone is started or completed.
- Technical debt or critical constraints are identified.
