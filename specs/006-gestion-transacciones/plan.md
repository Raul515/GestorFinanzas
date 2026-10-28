# Plan de Implementación: Especificación 006 — Historial y Gestión de Transacciones (Eliminación Segura y Reversión del Fondo de Emergencia)

Este plan técnico desglosa la implementación de la **Especificación 006** en 3 fases secuenciales estrictas. Siguiendo la gobernanza SDD (*Spec-Anchored*), cada fase requiere el 100% de pruebas automatizadas pasando y la confirmación explícita del usuario antes de iniciar la siguiente.

---

### Fase 1: Capa de Persistencia y Reversión Atómica (Backend)

- **Objetivo**: Implementar el método de eliminación de transacciones con lógica de reversión del saldo de `EmergencyFund` si la transacción corresponde a dicha subcategoría.
- **Archivos a crear/modificar**:
  - `src/backend/database/interfaz/db_interface.py` [MODIFICADO: definición de `delete_transaction`]
  - `src/backend/database/componentes/sqlite_crud.py` [MODIFICADO: implementación de `delete_transaction` con reversión]
  - `tests/unit/test_transactions_repository.py` [NUEVO: suite unitaria de persistencia]
- **Casos de Prueba a Verificar**:
  - Eliminación de transacción estándar.
  - Eliminación de transacción de fondo de emergencia con reducción exacta del saldo acumulado.
  - Intento de eliminación de ID inexistente.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_transactions_repository.py
  ```
- **Criterio de Aceptación**: 100% de pruebas unitarias de persistencia pasando.

---

### Fase 2: Endpoint REST y Pruebas de Integración (API FastAPI)

- **Objetivo**: Exponer la operación de eliminación a través de la API REST de FastAPI con códigos de estado HTTP estándar.
- **Archivos a crear/modificar**:
  - `src/backend/api/routers/transactions.py` [MODIFICADO: endpoint `@router.delete("/{transaction_id}")`]
  - `tests/integration/test_transactions_api.py` [NUEVO: pruebas de integración para eliminación de transacciones]
- **Casos de Prueba a Verificar**:
  - Respuesta HTTP `200 OK` y JSON `{ "status": "deleted", "transaction_id": ... }` al eliminar una transacción existente.
  - Respuesta HTTP `404 Not Found` al intentar eliminar un ID inexistente.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/integration/test_transactions_api.py
  ```
- **Criterio de Aceptación**: 100% de pruebas de integración pasando.

---

### Fase 3: Integración en Frontend Streamlit (Cliente y UI)

- **Objetivo**: Incorporar la llamada en el cliente HTTP frontend e implementar la interfaz de usuario con expander, tabla detallada y confirmación de borrado.
- **Archivos a crear/modificar**:
  - `src/frontend/api_client.py` [MODIFICADO: método `delete_transaction(transaction_id)` con observabilidad y logging]
  - `src/frontend/app.py` [MODIFICADO: expander *"📋 Historial de Transacciones de {nombre_mes}"* con tabla, botón de borrado y recálculo reactivo con `st.rerun()`]
  - `tests/unit/test_sanity.py` [MODIFICADO: prueba unitaria de `delete_transaction` en cliente frontend]
  - `MEMORY.md` [MODIFICADO: registro de cierre de Spec 006]
  - `specs/README.md` [MODIFICADO: actualización de estado a Completada]
- **Casos de Prueba a Verificar**:
  - Prueba de llamada cliente en `tests/unit/test_sanity.py`.
  - Verificación interactiva del flujo en Streamlit.
- **Puerta de Verificación**:
  ```powershell
  .\venv\Scripts\pytest -v tests/unit/test_sanity.py tests/unit/test_transactions_repository.py tests/integration/test_transactions_api.py
  ```
- **Criterio de Aceptación**: 100% de pruebas de la especificación pasando.
