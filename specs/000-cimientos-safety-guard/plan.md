# Plan de Implementación Técnica: Spec 000 — Cimientos, Servicios Desacoplados y Safety Guard

## 1. Resumen Ejecutivo
Este plan técnico detalla los pasos de ingeniería para implementar la [Spec 000](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/000-cimientos-safety-guard/spec.md), resolviendo las deficiencias arquitectónicas actuales y preparando el sistema para la integración de agentes de inteligencia financiera.

El trabajo se divide en 6 fases estrictamente secuenciales con puertas de calidad verificables en cada etapa.

---

## 2. Arquitectura de Archivos y Componentes

```
GestorFinanzas/
├── pytest.ini                                      [NUEVO] Configuración raíz de pytest
├── requirements/
│   ├── backend.txt                                 [MODIFICADO] Dependencias runtime backend
│   └── dev.txt                                     [NUEVO] pytest, httpx para pruebas
├── tests/                                          [NUEVO] Directorio de pruebas
│   ├── conftest.py                                 [NUEVO] Fixtures de SQLite en memoria y FastAPI TestClient
│   ├── unit/
│   │   ├── test_financial_calculator.py           [NUEVO] Tests unitarios 50/30/20 y métricas
│   │   └── test_safety_guard_service.py           [NUEVO] Tests unitarios de lógica del Safety Guard
│   └── integration/
│       ├── test_safety_guard_api.py               [NUEVO] Tests de endpoints /advisor/* con TestClient
│       └── test_emergency_fund_sync.py            [NUEVO] Tests de sincronización transaccional
├── src/
│   ├── backend/
│   │   ├── api/
│   │   │   ├── main.py                             [MODIFICADO] Registro de router safety_guard
│   │   │   └── routers/
│   │   │       ├── safety_guard.py                 [NUEVO] Endpoints /advisor/safety-status y config
│   │   │       └── transacciones.py                [MODIFICADO] Hook para sincronizar saldo del fondo
│   │   ├── database/
│   │   │   ├── componentes/
│   │   │   │   ├── sqlite_db.py                    [MODIFICADO] Registro de modelo EmergencyFund
│   │   │   │   └── sqlite_crud.py                  [MODIFICADO] Métodos CRUD para EmergencyFund
│   │   │   └── interfaz/
│   │   │       └── db_interface.py                 [MODIFICADO] Interfaz IEmergencyFundRepository
│   │   ├── domain/
│   │   │   ├── models/
│   │   │   │   └── emergency_fund.py               [NUEVO] Modelo SQLAlchemy Declarative Mapped
│   │   │   └── schemas/
│   │   │       └── emergency_fund.py               [NUEVO] Schemas Pydantic v2 de entrada y salida
│   │   └── services/
│   │       ├── __init__.py                         [NUEVO]
│   │       ├── financial_calculator.py             [NUEVO/MIGRADO] Lógica desacoplada 50/30/20
│   │       └── safety_guard.py                     [NUEVO] Servicio puro de cálculo del Safety Guard
│   └── frontend/
│       ├── api_client.py                           [MODIFICADO] Métodos de llamada a /advisor/*
│       ├── app.py                                  [MODIFICADO] Visualización del Safety Guard y ajuste
│       └── services/
│           └── financial_calculator.py             [MODIFICADO] Re-export compatible hacia backend
```

---

## 3. Desglose Fase por Fase

### Fase 1: Infraestructura de Pruebas (`pytest` + `dev.txt`)
- **Objetivo**: Habilitar la ejecución de pruebas automatizadas en local con `.\venv\Scripts\pytest`.
- **Acciones**:
  1. Crear `requirements/dev.txt` con:
     ```
     pytest>=8.0.0
     httpx>=0.27.0
     ```
  2. Instalar dependencias en el entorno virtual activo `venv`.
  3. Crear `pytest.ini` en la raíz:
     ```ini
     [pytest]
     testpaths = tests
     pythonpath = src
     python_files = test_*.py
     python_functions = test_*
     ```
  4. Crear `tests/conftest.py` con fixtures:
     - `db_session`: Sesión SQLAlchemy conectada a SQLite en memoria (`sqlite:///:memory:`) con tablas creadas en setup y destruidas en teardown.
     - `client`: `TestClient(app)` para pruebas HTTP directas sin levantar servidor.
     - `seed_data`: Categorías estándar inicializadas (Ingresos Netos, Necesidades Básicas, Deseos, Ahorro e Inversión) y subcategoría "Fondo de emergencia".
- **Criterio de Verificación**: `.\venv\Scripts\pytest` ejecuta y reporta 0 errores.

---

### Fase 2: Desacoplamiento de Servicios Financieros
- **Objetivo**: Mover las funciones matemáticas puras de `src/frontend/services/financial_calculator.py` a `src/backend/services/financial_calculator.py`, con tipado estricto y tests unitarios.
- **Acciones**:
  1. Crear `src/backend/services/financial_calculator.py` con tipado riguroso:
     - `calculate_category_totals(...)`
     - `calculate_503020_percentages(...)`
     - `calculate_annual_metrics(...)`
     - `get_monthly_needs_budget(presupuestos, subcategorias, categoria_necesidades_id) -> float`
  2. Convertir `src/frontend/services/financial_calculator.py` en un re-exportador compatible para evitar romper cualquier import existente:
     ```python
     from backend.services.financial_calculator import *
     ```
  3. Crear `tests/unit/test_financial_calculator.py`:
     - Test de cálculo 50/30/20 exacto sobre presupuesto base.
     - Test de cálculo con ingresos cero (evitar división por cero).
     - Test de saldo 'Sin Asignar'.
     - Test de desviaciones anuales.
- **Criterio de Verificación**: Todos los tests unitarios pasan al 100%.

---

### Fase 3: Modelo y Capa de Datos del Fondo de Emergencia
- **Objetivo**: Persistir en SQLite el estado del Fondo de Emergencia (`emergency_funds`).
- **Acciones**:
  1. Crear `src/backend/domain/models/emergency_fund.py`:
     ```python
     from datetime import datetime
     from sqlalchemy import Float, Integer, Boolean, DateTime, func
     from sqlalchemy.orm import Mapped, mapped_column
     from .base import Base

     class EmergencyFund(Base):
         __tablename__ = "emergency_funds"

         id: Mapped[int] = mapped_column(primary_key=True, index=True)
         current_balance: Mapped[float] = mapped_column(Float, default=0.0)
         target_months: Mapped[int] = mapped_column(Integer, default=3)
         target_amount: Mapped[float] = mapped_column(Float, default=0.0)
         is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
         updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
     ```
  2. Crear schemas Pydantic en `src/backend/domain/schemas/emergency_fund.py`:
     - `EmergencyFundConfigUpdate`: validación `target_months >= 3`, `current_balance >= 0.0`.
     - `EmergencyFundResponse`: DTO serializable con todos los atributos.
     - `SafetyStatusResponse`: DTO con `current_balance`, `target_amount`, `coverage_months`, `target_months`, `is_completed`, `can_invest`, `gap`, `monthly_needs_reference`, `message`.
  3. Modificar `src/backend/database/componentes/sqlite_db.py`:
     - En `init_db()`, importar `emergency_fund` para que `Base.metadata.create_all()` cree la tabla automáticamente.
  4. Extender `src/backend/database/interfaz/db_interface.py`:
     - Crear `IEmergencyFundRepository` y añadirlo a `IRepository`.
  5. Implementar métodos en `src/backend/database/componentes/sqlite_crud.py`:
     - `get_or_create_emergency_fund() -> EmergencyFund`
     - `update_emergency_fund(update_data) -> EmergencyFund`
     - `adjust_emergency_fund_balance(delta: float) -> EmergencyFund`
- **Criterio de Verificación**: Pruebas de integración de persistencia y consultas en base de datos pasan limpiamente.

---

### Fase 4: Lógica de Negocio del Safety Guard
- **Objetivo**: Implementar el servicio puro `SafetyGuardService` que evalúa dinámicamente el cumplimiento y la sincronización con transacciones.
- **Acciones**:
  1. Crear `src/backend/services/safety_guard.py`:
     - Función `evaluate_safety_status(fund: EmergencyFund, monthly_needs: float) -> SafetyStatusResponse`:
       - `target_amount = fund.target_months * monthly_needs`
       - `coverage_months = (fund.current_balance / monthly_needs) if monthly_needs > 0 else 0.0`
       - `is_completed = fund.current_balance >= target_amount and monthly_needs > 0`
       - `can_invest = is_completed`
       - `gap = max(0.0, target_amount - fund.current_balance)`
       - Mensaje contextual en español (ej. *"Fondo cubierto: 3.5 meses de gastos esenciales. Habilitado para invertir."* o *"Fondo incompleto: 1.2 / 3.0 meses cubiertos. Se requiere aportar 1.450,00 € antes de autorizar activos de riesgo."*).
  2. Modificar el router de transacciones `src/backend/api/routers/transacciones.py`:
     - Al crear una transacción: si la subcategoría corresponde a "Fondo de emergencia", sincronizar el `current_balance` del fondo.
  3. Crear `tests/unit/test_safety_guard_service.py`:
     - Test con saldo 0 $\to$ `can_invest = False`.
     - Test con saldo parcial $\to$ `can_invest = False`, brecha calculada correctamente.
     - Test con saldo completo $\to$ `can_invest = True`.
     - Test de rechazo de meses $< 3$.
- **Criterio de Verificación**: Pruebas unitarias de transiciones y cálculos del Safety Guard pasan al 100%.

---

### Fase 5: Exposición de Endpoints REST
- **Objetivo**: Exponer las funcionalidades del Safety Guard a través de FastAPI.
- **Acciones**:
  1. Crear `src/backend/api/routers/safety_guard.py`:
     - `GET /advisor/safety-status`: Devuelve el diagnóstico completo del estado de seguridad y capacidad de inversión.
     - `GET /advisor/emergency-fund`: Devuelve la configuración actual del fondo.
     - `POST /advisor/emergency-fund/config`: Actualiza meses objetivo (validando $\ge 3$) y/o saldo acumulado manual.
  2. Registrar el router en `src/backend/api/main.py`:
     ```python
     from backend.api.routers import safety_guard
     app.include_router(safety_guard.router)
     ```
  3. Crear `tests/integration/test_safety_guard_api.py`:
     - Pruebas HTTP con `TestClient`: llamada a `/advisor/safety-status` y `/advisor/emergency-fund/config`.
- **Criterio de Verificación**: Endpoints devuelven códigos HTTP 200 y validaciones HTTP 400/422 con tests automatizados.

---

### Fase 6: Integración en Frontend Streamlit
- **Objetivo**: Conectar el frontend existente con el Safety Guard y ofrecer al usuario visibilidad y control sobre su fondo de emergencia.
- **Acciones**:
  1. Modificar `src/frontend/api_client.py`:
     - Añadir `get_safety_status() -> Optional[Dict[str, Any]]`
     - Añadir `update_emergency_fund_config(target_months: int, current_balance: Optional[float] = None)`
  2. Modificar `src/frontend/app.py`:
     - En la pestaña o sección de presupuesto/ahorro, integrar una tarjeta o widget resumen del Fondo de Emergencia:
       - Métrica principal: Saldo actual vs Meta (`current_balance` / `target_amount`).
       - Barra de progreso y meses cubiertos (`coverage_months` / `target_months`).
       - Etiqueta de estado: Badge verde "Protegido (Inversión habilitada)" o badge ámbar "En construcción (Riesgo bloqueado)".
       - Cuadro desplegable para configurar meses objetivo ($\ge 3$) y ajustar saldo inicial.
       - Si `is_completed == True`: mostrar recomendación de destinar 0 € este mes a la subcategoría *"Fondo de emergencia"*.
- **Criterio de Verificación**: El frontend arranca sin advertencias de dependencias rotas, consume la API correctamente y muestra el estado dinámico.

---

## 4. Matriz de Verificación y Criterios de Aceptación

| Componente | Verificación | Comando / Prueba |
| :--- | :--- | :--- |
| **Infraestructura de Tests** | Pytest instalado y operativo | `.\venv\Scripts\pytest` |
| **Fórmulas 50/30/20** | Tests unitarios pasan al 100% | `tests/unit/test_financial_calculator.py` |
| **Lógica Safety Guard** | Tests de cobertura y bloqueo pasan | `tests/unit/test_safety_guard_service.py` |
| **Endpoints REST** | Status code 200 y validación $\ge 3$ meses | `tests/integration/test_safety_guard_api.py` |
| **Sincronización Transacciones** | Transacción en fondo actualiza saldo | `tests/integration/test_emergency_fund_sync.py` |
| **Tipado Estático** | Cero errores de tipos | `.\venv\Scripts\python -m pyright` |
| **Frontend Streamlit** | Cero regresiones visuales o de importación | `.\venv\Scripts\streamlit run src/frontend/app.py` |

---

## 5. Control de Regresiones y Compatibilidad
1. **Backwards Compatibility en Frontend**: `src/frontend/services/financial_calculator.py` continuará exportando los mismos nombres de funciones hacia `app.py`.
2. **Tablas SQLite Existentes**: La creación de `emergency_funds` mediante `create_all()` no altera ninguna de las tablas existentes (`categorias`, `subcategorias`, `presupuestos_mensuales`, `transacciones`).
3. **Semilla Inicial**: Si no existe ningún registro en `emergency_funds`, el sistema creará automáticamente el registro inicial con `target_months=3` y `current_balance=0.0`.
