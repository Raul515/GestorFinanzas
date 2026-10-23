# Especificación: Cimientos, Servicios Desacoplados y Safety Guard (Fondo de Emergencia)

## 1. Contexto y Objetivo
El Gestor de Finanzas Personales opera actualmente con una arquitectura cliente-servidor (FastAPI + Streamlit + SQLite local) bajo la metodología 50/30/20. Sin embargo, antes de incorporar agentes de inteligencia financiera y análisis de mercado (Specs 001 a 005), el sistema presenta tres deficiencias estructurales críticas respecto a la **Constitución**:
1. **Ausencia de Tests Automatizados**: No existe una suite de pruebas con `pytest` que verifique matemáticamente los cálculos de reparto 50/30/20, desviaciones ni saldos no asignados (violando el Principio 4: *Veracity & Testing*).
2. **Lógica Contable Acoplada al Frontend**: Existen funciones de cálculo financiero ubicadas en `src/frontend/services/financial_calculator.py` e inline en `app.py`, lo que impide que agentes o servicios del backend consuman la lógica de negocio de forma independiente (violando el Principio 3: *Decoupled Logic*).
3. **Inexistencia de Entidad y Servicio Formal para el Fondo de Emergencia**: La subcategoría *"Fondo de emergencia"* existe en la base de datos únicamente como un concepto presupuestario de gasto/ahorro mensual (flujo), pero no existe una entidad que registre el saldo acumulado real (stock), ni un servicio que evalúe si se cubren los 3 meses mínimos de necesidades básicas exigidos por el Principio 5 (*Safety Guard*).

El **objetivo** de esta especificación es sentar los cimientos de ingeniería del proyecto:
- Configurar la infraestructura de pruebas automatizadas con `pytest`.
- Desacoplar la lógica financiera 50/30/20 en servicios backend puros y testeados.
- Modelar en la base de datos la entidad del **Fondo de Emergencia** (`EmergencyFund`) con saldo real, meses de cobertura configurables (mínimo 3) y ajuste dinámico en función del presupuesto base de Necesidades Básicas.
- Crear el servicio y endpoints del **Safety Guard** que dictaminarán objetivamente si el usuario está habilitado para recibir recomendaciones de inversión en activos de riesgo.

---

## 2. Usuarios
- **Desarrollador / Auditor de Calidad**: Necesita una suite de pruebas automatizadas que valide numéricamente cualquier cambio en las reglas de negocio antes de liberar nuevas funcionalidades.
- **Ahorrador / Usuario del Gestor**: Necesita visibilidad exacta sobre su colchón de seguridad real, saber cuánto debe aportar mensualmente para completarlo, y contar con la garantía de que el sistema nunca le incentivará a invertir en riesgo si su fondo no está cubierto.

---

## 3. Historias de Usuario
- **HU-1 (Monitoreo del Fondo de Emergencia)**: Como usuario, quiero consultar en cualquier momento el estado detallado de mi fondo de emergencia (saldo actual acumulado, meta en euros, meses cubiertos y porcentaje de cumplimiento) para tener certeza sobre mi solvencia ante imprevistos.
- **HU-2 (Configuración y Saldo Inicial)**: Como usuario, quiero poder configurar el número de meses de cobertura deseados (con un mínimo de 3 meses) y fijar o ajustar manualmente mi saldo real acumulado para reflejar mis ahorros bancarios previos.
- **HU-3 (Sincronización Mensual Automática)**: Como usuario, quiero que cuando registre una aportación mensual en la subcategoría *"Fondo de emergencia"*, mi saldo acumulado se actualice automáticamente, y que si el fondo ya está completo, el sistema sugiera destinar 0 € a esa subcategoría para liberar el ahorro hacia la inversión.
- **HU-4 (Reajuste Dinámico por Variación de Gastos Fijos)**: Como usuario, quiero que si mis gastos de necesidades básicas presupuestados aumentan (ej. subida de alquiler o suministros), la meta del fondo de emergencia se incremente de forma automática y el sistema me indique el nuevo importe a aportar hasta cubrir la diferencia.
- **HU-5 (Salvaguarda Estricta contra Riesgos)**: Como usuario prudente, quiero que cualquier intento de consultar o recibir sugerencias sobre activos de riesgo quede formalmente vetado o condicionado por el sistema si mi fondo de emergencia no cubre los meses mínimos requeridos.
- **HU-6 (Fiabilidad Verificada por Tests)**: Como mantenedor del sistema, quiero ejecutar `pytest` y verificar que el 100% de las fórmulas financieras (regla 50/30/20, desviaciones presupuestarias, saldos acumulados y lógica del Safety Guard) son matemáticamente consistentes y reproducibles.

---

## 4. Requisitos Funcionales (RF)

### RF-1: Suite de Pruebas Automatizadas (pytest)
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE contar con una suite de pruebas automatizadas ejecutable mediante `pytest` que valide de forma aislada e independiente de la interfaz gráfica todos los cálculos matemáticos, repartos porcentuales y transiciones de estado del Safety Guard.
- **Criterio EARS (Unwanted Behavior)**: SI alguna prueba unitaria o de integración de cálculo financiero falla, ENTONCES EL SISTEMA DEBE impedir considerar válida la implementación o dar por cerrado el hito de desarrollo.

### RF-2: Desacoplamiento de Servicios Financieros en Backend
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE albergar toda la lógica matemática del modelo 50/30/20 (cálculo de ingresos netos, techos por categoría 50%, 30%, 20%, desviaciones de gasto real vs presupuesto y cálculo de fondos no asignados) exclusivamente dentro de módulos y servicios del backend.
- **Criterio EARS (Event-driven)**: CUANDO el frontend de Streamlit requiera métricas presupuestarias o de cumplimiento, EL SISTEMA DEBE suministrarlas mediante llamadas a los servicios y endpoints del backend, restringiendo el frontend a la presentación visual.

### RF-3: Entidad de Persistencia del Fondo de Emergencia
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE registrar en la base de datos SQLite local una entidad persistente para el Fondo de Emergencia con los siguientes atributos mínimos:
  - `current_balance`: Saldo monetario actual disponible en el fondo (€).
  - `target_months`: Número entero de meses de gastos de necesidades a cubrir (valor por defecto: 3).
  - `target_amount`: Importe monetario objetivo calculado (€).
  - `is_completed`: Estado booleano que indica si `current_balance >= target_amount`.
  - `updated_at`: Marca temporal de última actualización.
- **Criterio EARS (Unwanted Behavior)**: SI el usuario intenta configurar un valor de `target_months` inferior a 3, ENTONCES EL SISTEMA DEBE rechazar la configuración informando de que 3 meses es el mínimo innegociable establecido por la Constitución.

### RF-4: Sincronización Transaccional del Saldo Acumulado
- **Criterio EARS (Event-driven)**: CUANDO se registra, modifica o elimina una transacción contable asociada a la subcategoría *"Fondo de emergencia"*, EL SISTEMA DEBE recalcular y sincronizar el `current_balance` del fondo de emergencia en consonancia con el importe aportado o retirado.
- **Criterio EARS (Event-driven)**: CUANDO el usuario modifica manualmente el `current_balance` a través de la interfaz de ajuste de saldo, EL SISTEMA DEBE actualizar el saldo registrado y evaluar inmediatamente el nuevo estado de cobertura.

### RF-5: Cálculo Dinámico de la Meta por Presupuesto Base
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE calcular el `target_amount` del fondo de emergencia multiplicando el número de meses configurado (`target_months`) por el total mensual presupuestado para la categoría *"Necesidades Básicas"* correspondiente al mes o plantilla activa.
- **Criterio EARS (Event-driven)**: CUANDO se modifica al alza o a la baja el presupuesto de la categoría *"Necesidades Básicas"*, EL SISTEMA DEBE recalcular automáticamente el `target_amount` y reevaluar si `current_balance >= target_amount`.

### RF-6: Reajuste Automático del Flujo Mensual de Ahorro
- **Criterio EARS (State-driven)**: MIENTRAS el fondo de emergencia se encuentre completado (`is_completed == True`), EL SISTEMA DEBE sugerir un importe de 0 € para la subcategoría *"Fondo de emergencia"* en la asignación presupuestaria mensual, liberando el tramo de ahorro restante para inversión o metas patrimoniales.
- **Criterio EARS (State-driven)**: MIENTRAS el fondo de emergencia no alcance la meta objetivo (`is_completed == False`), EL SISTEMA DEBE calcular el déficit (`target_amount - current_balance`) y priorizar la asignación de ahorro mensual hacia la subcategoría *"Fondo de emergencia"* hasta cerrar la brecha.

### RF-7: Servicio Backend Safety Guard
- **Criterio EARS (Ubiquitous)**: EL SISTEMA DEBE exponer un servicio y endpoint específico en FastAPI (`GET /advisor/safety-status`) que devuelva el estado cuantitativo de seguridad financiera:
  - Saldo actual (`current_balance`).
  - Meta objetivo (`target_amount`).
  - Meses de cobertura reales actuales (`current_balance / gasto_mensual_necesidades`).
  - Meses de cobertura objetivo (`target_months`).
  - Estado de autorización para inversión de riesgo (`can_invest: bool`), siendo `True` únicamente cuando `current_balance >= target_amount`.
  - Mensaje diagnóstico explicativo en español.
- **Criterio EARS (State-driven)**: MIENTRAS `can_invest` sea `False`, EL SISTEMA DEBE emitir un dictamen de bloqueo frente a cualquier recomendación o selección de activos de renta variable o instrumentos con riesgo de capital.

---

## 5. Requisitos No Funcionales (RNF)
- **RNF-1 (Precisión Numérica Financiera)**: Todos los cálculos de saldo, metas y porcentajes deben operar con precisión decimal adecuada para moneda (2 decimales), evitando discrepancias por errores de coma flotante.
- **RNF-2 (Rendimiento de Pruebas)**: La suite completa de pruebas de `pytest` debe ejecutarse en menos de 5 segundos en entorno local estándar.
- **RNF-3 (Privacidad y Almacenamiento Local)**: Todos los saldos, metas y datos de transacciones del fondo de emergencia residirán exclusivamente en la base de datos local SQLite (`finanzas.db`), sin sincronización ni envío a servicios externos.
- **RNF-4 (Convenciones de Idioma)**:
  - Código, nombres de tablas, columnas, clases, métodos y tests en **inglés**.
  - Textos de mensajes, diagnósticos, documentación y etiquetas de interfaz en **español**.

---

## 6. Casos Límite
1. **Usuario sin Presupuesto Registrado**: Si el usuario es nuevo y aún no ha configurado el presupuesto mensual ni la plantilla base de *"Necesidades Básicas"*, el gasto de referencia es 0. En este caso, el sistema debe indicar que se requiere configurar primero el presupuesto base para determinar la meta, manteniendo `can_invest = False`.
2. **Retiro por Emergencia Real**: Si el usuario sufre un imprevisto y retira dinero del fondo (reduciendo `current_balance` por debajo de `target_amount`), el sistema debe pasar de inmediato `is_completed` a `False` y reactivar las alertas y el bloqueo de activos de riesgo.
3. **Reducción de Gastos en Necesidades Básicas**: Si el usuario reduce sus gastos fijos de necesidades básicas (ej. cancelación de una suscripción básica o mudanza a alquiler más bajo), el `target_amount` disminuye. Si `current_balance` supera la nueva meta, el sistema debe reflejar una cobertura superior al 100% sin generar desbordamientos ni errores.
4. **Cero Fondos Disponibles**: Si `current_balance` es 0 €, la cobertura en meses debe reportarse como `0.0` meses sin producir excepciones de división por cero.

---

## 7. Fuera de Alcance (Out of Scope)
- Integración con APIs externas de cotizaciones de mercado (corresponde a Specs 001, 002 y 003).
- Modelos LLM o agentes LangGraph (corresponden a Spec 004 y 005).
- Creación de nuevas pantallas visuales de mercado o screener en Streamlit (se mantiene la UI actual añadiendo únicamente la visualización y edición del fondo de emergencia en su pestaña correspondiente).

---

## 8. Criterios de Finalización (Definition of Done)
1. **Configuración de Pytest**: Ejecución limpia de `pytest` en la raíz del proyecto pasando el 100% de los tests creados.
2. **Servicios Financieros Backend**: `financial_calculator.py` reubicado en backend (`src/backend/services/`), tipado y desacoplado de Streamlit, con tests unitarios exhaustivos para cada cálculo 50/30/20.
3. **Modelo de Datos SQLite**: Tabla `emergency_funds` creada y migrada limpiamente en `src/backend/database/models.py`.
4. **Servicio y Endpoints Safety Guard**: Endpoint `GET /advisor/safety-status` y endpoint de configuración/ajuste de saldo `POST /advisor/emergency-fund` operativos y probados con tests de integración.
5. **Cero Regresiones**: La aplicación Streamlit existente arranca y funciona con normalidad utilizando los servicios backend sin errores de importación.
6. **Revisión Constitucional**: Verificación expresa de que se cumplen los 7 principios de [docs/constitution.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/docs/constitution.md).

---

## 9. Dudas Abiertas
- *Ninguna bloqueante identificada para esta especificación*. Las posibles mejoras avanzadas (como el cálculo mixto por media móvil de 3 meses frente a presupuesto base) quedan catalogadas para iteraciones posteriores según lo acordado.
