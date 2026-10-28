# Especificación 006: Historial y Gestión de Transacciones (Eliminación Segura y Reversión del Fondo de Emergencia)

## 1. Resumen Ejecutivo y Visión

Actualmente, el **Gestor de Finanzas Personales** permite a los usuarios registrar transacciones contables mensuales a través del formulario interactivo *"Añadir Transacción Real"* en cada pestaña mensual. Sin embargo, el sistema presenta dos carencias funcionales críticas:

1. **Falta de Visibilidad Transaccional Individual**: En la interfaz de Streamlit solo se reflejan los valores acumulados en las tablas comparativas y gráficos de cada mes. El usuario no dispone de un visor o listado donde pueda consultar las transacciones individuales que conforman dichos totales (fecha, concepto, importe y notas).
2. **Imposibilidad de Corrección sin Acceso a la Base de Datos**: Si un usuario comete un error al teclear un importe, seleccionar una subcategoría o ingresar una fecha, no existe ningún mecanismo en la aplicación para eliminar o rectificar la transacción. Esto obliga a realizar intervenciones manuales por consola o scripts SQL en `finanzas.db`.
3. **Riesgo de Inconsistencia en la Salvaguarda de Seguridad (Principio 5 y 9)**: Al registrar una transacción en la subcategoría *"Fondo de emergencia"*, el repositorio incrementa automáticamente el saldo acumulado en la entidad `EmergencyFund`. Si una transacción errónea se elimina directamente en base de datos sin un proceso controlado, el saldo del fondo queda desfasado respecto a las transacciones reales.

El **objetivo** de esta especificación es implementar el ciclo de gestión de transacciones en la interfaz de usuario:
- Proporcionar un **desplegable interactivo con el historial completo de transacciones del mes**.
- Habilitar un **mecanismo de eliminación directa y segura con solicitud de confirmación** para evitar borrados accidentales.
- Garantizar la **reversión atómica y automática del saldo del Fondo de Emergencia** si la transacción eliminada correspondía a dicha subcategoría.
- Ofrecer respuesta en tiempo real en la UI actualizando métricas, balances 50/30/20 y tablas inmediatamente tras la eliminación.

---

## 2. Usuarios y Casos de Uso

- **Usuario del Gestor (Ahorrador / Inversor)**:
  - Necesita verificar qué transacciones ha registrado durante el mes en curso o meses pasados para auditar sus gastos.
  - Necesita eliminar de manera rápida y sin fricción cualquier apunte contable duplicado o erróneo.
- **Sistema Contable y Salvaguarda Patrimonial**:
  - Requiere que cualquier alteración o supresión de apuntes mantenga la coherencia matemática de la regla 50/30/20 y la exactitud del saldo real del fondo de emergencia.

---

## 3. Historias de Usuario (HU)

- **HU-1 (Visor de Historial Mensual)**: Como usuario, quiero ver en cada pestaña de mes un historial detallado con todas las transacciones registradas (fecha, subcategoría, categoría, importe y notas) para tener control total sobre mis apuntes.
- **HU-2 (Eliminación con Confirmación)**: Como usuario, quiero presionar un botón de eliminar junto a cualquier transacción errónea y que el sistema me solicite una confirmación explícita antes de ejecutar el borrado, evitando pérdidas accidentales de datos.
- **HU-3 (Reversión Transaccional del Fondo de Emergencia)**: Como usuario, quiero que si elimino una aportación previa al Fondo de Emergencia, el sistema reste de forma automática e inmediata dicho importe de mi saldo acumulado del fondo, manteniendo mi estatus de seguridad sincronizado.
- **HU-4 (Actualización Inmediata en Pantalla)**: Como usuario, quiero que al eliminar una transacción las tablas de Presupuesto vs Real, métricas superiores y gráficos se recalculen y actualicen al instante sin necesidad de refrescar el navegador.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Interfaz y Métodos en Repositorio Backend (`ITransactionRepository` / `SQLiteRepository`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE definir en `ITransactionRepository` el método `delete_transaction(self, transaction_id: int) -> bool`.
- **Criterio EARS (Event-driven)**: CUANDO se invoca `delete_transaction(transaction_id)`:
  1. El repositorio buscará el registro en la tabla `transactions` por su clave primaria `id`.
  2. Si el registro no existe, devolverá `False`.
  3. Si el registro existe, identificará su `subcategory_id`. Si dicha subcategoría corresponde al *"Fondo de emergencia"* (búsqueda insensible a mayúsculas en el nombre), el repositorio invocará `self.adjust_emergency_fund_balance(-db_item.amount)`, restando el importe de forma atómica.
  4. El repositorio eliminará físicamente el registro de la tabla `transactions`, ejecutará `commit` y devolverá `True`.

### RF-2: Endpoint REST en FastAPI (`/transactions/{transaction_id}`)
- **Criterio EARS (Event-driven)**: CUANDO el cliente emite una petición `DELETE /transactions/{transaction_id}`:
  - Si la transacción existe y se elimina satisfactoriamente, EL SISTEMA DEBE responder con código HTTP `200 OK` y el JSON:
    ```json
    {
      "status": "deleted",
      "transaction_id": 123
    }
    ```
  - Si la transacción no existe, EL SISTEMA DEBE responder con código HTTP `404 Not Found` y detalle `"Transaction not found"`.

### RF-3: Cliente Frontend con Observabilidad (`src/frontend/api_client.py`)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE incorporar la función `delete_transaction(transaction_id: int) -> bool` en `api_client.py`.
- **Criterio EARS (Unwanted Behavior)**: SI la llamada al backend falla por desconexión de red o error HTTP (4xx/5xx), EL SISTEMA DEBE registrar el incidente mediante `logger.error` con la URL y código correspondiente (cumpliendo con la prohibición de fallos silenciosos y el Principio 13) y retornar `False`.

### RF-4: Componente de Historial y Eliminación en Streamlit (`src/frontend/app.py`)
- **Criterio EARS (Ubiquitous)**: En cada pestaña de mes (Meses 1 al 12), EL SISTEMA DEBE renderizar un bloque expandible:
  `st.expander(f"📋 Historial de Transacciones de {nombre_mes}")`.
- **Criterio EARS (State-driven)**: MIENTRAS no existan transacciones registradas en el mes, EL SISTEMA DEBE mostrar un mensaje informativo: *"No hay transacciones registradas en este mes."*
- **Criterio EARS (State-driven)**: MIENTRAS existan transacciones en el mes, EL SISTEMA DEBE mostrar un listado/tabla formateada con las siguientes columnas:
  - **Fecha**: Formato `YYYY-MM-DD`.
  - **Concepto / Subcategoría**: Nombre legible en español.
  - **Categoría**: Ingresos Netos, Necesidades Básicas, Deseos o Ahorro e Inversión.
  - **Importe**: Formato monetario `#,##0.00 €`.
  - **Descripción**: Texto ingresado por el usuario o guión si está vacío.
  - **Acción**: Botón o menú emergente de confirmación `🗑️ Eliminar`.
- **Criterio EARS (Event-driven)**: CUANDO el usuario confirma la eliminación de una transacción:
  - Se llamará a `api_client.delete_transaction(t_id)`.
  - Si es exitoso, se notificará con `st.toast("Transacción eliminada correctamente", icon="🗑️")` y se ejecutará `st.rerun()` para recalcular balances y tablas en tiempo real.
  - Si falla, se notificará con `st.error("Error al intentar eliminar la transacción.")`.

---

## 5. Requisitos No Funcionales (RNF)

- **RNF-1 (Convención de Idioma - Opción 1)**:
  - Código backend, rutas, métodos de base de datos y esquemas Pydantic 100% en inglés: `delete_transaction`, `transaction_id`, `/transactions/{transaction_id}`.
  - Interfaz de usuario de Streamlit, botones, notificaciones y documentación 100% en español.
- **RNF-2 (Observabilidad y Cero Fallos Silenciosos)**:
  - Prohibido silenciar excepciones mediante `pass`. Todas las operaciones de eliminación y reversión de fondos deben registrarse con niveles `logger.info` o `logger.error`.
- **RNF-3 (Pruebas Automatizadas Obligatorias)**:
  - Cobertura completa con `pytest` para la reversión del fondo, la eliminación de transacciones y el endpoint de la API. Mantener el 100% de la suite pasando antes de cerrar cada fase.

---
