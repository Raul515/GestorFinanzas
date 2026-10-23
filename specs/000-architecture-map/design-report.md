# Informe de Diseño Arquitectónico: Inteligencia Financiera

## Contexto

El gestor actual opera con 4 categorías fijas (Ingresos Netos, Necesidades Básicas, Deseos, Ahorro e Inversión), 3 tablas SQLAlchemy (`categorias`, `subcategorias`, `presupuestos_mensuales`, `transacciones`), 3 routers FastAPI y un monolito Streamlit de 678 líneas con la lógica 50/30/20 parcialmente extraída a `financial_calculator.py`. No existe infraestructura de tests, ni modelos de mercado, ni integración con LangGraph.

La ampliación incorpora 4 vistas nuevas en Streamlit + un backend de agentes LangGraph que accede a datos de mercado externos y a la BD local, respetando la Constitución (privacidad local, fondo de emergencia, veracidad).

---

## 1. Descomposición en Specs (Orden Secuencial)

### Spec 000 — Cimientos: Tests, Servicios Desacoplados y Fondo de Emergencia
- **Objetivo**: Establecer la infraestructura de tests con `pytest`, mover la lógica financiera restante de `app.py` a servicios backend testables, y crear el servicio de cálculo del Fondo de Emergencia (Safety Guard) que todas las specs posteriores necesitan.
- **Justificación**: El Principio 4 (Veracity & Testing) exige tests automáticos como puerta de avance. El Principio 5 (Safety Guard) requiere un cálculo formalizado del fondo de emergencia antes de que cualquier funcionalidad de mercado pueda evaluarlo. Actualmente `financial_calculator.py` vive en `src/frontend/services/` (viola Principio 3: Decoupled Logic). Además, la subcategoría "Fondo de emergencia" ya existe en la BD bajo "Ahorro e Inversión", pero no hay ningún servicio que calcule su saldo acumulado ni lo compare contra 3 meses de gastos fijos.
- **Dependencias**: Ninguna. Es el primer paso obligatorio.
- **Entregables clave**:
  - Configuración de `pytest` y primer conjunto de tests para `financial_calculator`.
  - Servicio backend `safety_guard` con cálculo del saldo del fondo de emergencia y la comparación contra gastos fijos esenciales (promedio de los últimos 3 meses de transacciones en categoría "Necesidades Básicas").
  - Migración de `financial_calculator.py` de frontend a backend.

### Spec 001 — Radar Macro y Noticias
- **Objetivo**: Vista de Streamlit que muestra contexto macroeconómico y noticias financieras filtradas con puntuación de impacto (Bajo/Medio/Alto), sin sensacionalismo.
- **Dependencias**: Spec 000 (tests + servicio Safety Guard operativo).
- **Skill asociada**: `market-news-analyst`.
- **Puntos críticos**: Selección de API de noticias gratuita y sin autenticación con fricción, formato determinista de la puntuación de impacto.

### Spec 002 — Screener y Oportunidades (Filtrado Cuantitativo)
- **Objetivo**: Motor de screener que filtra acciones y ETFs por ratios financieros (PER, EV/EBITDA, P/B, Dividend Yield), volumen y variación. Presenta resultados tabulares ordenables en una pestaña dedicada.
- **Dependencias**: Spec 000 (tests), Spec 001 no es bloqueante pero comparte la infraestructura de datos de mercado.
- **Skill asociada**: `tradingview-quantitative`, `stock-info-explorer` (extracción de datos vía `yfinance`).
- **Puntos críticos**: Universo inicial de tickers a filtrar (¿S&P 500, IBEX 35, configurable?), gestión de rate limiting de `yfinance`, caché local.

### Spec 003 — Análisis Fundamental (Deep Dive)
- **Objetivo**: Análisis contable riguroso bajo demanda de una empresa individual: Balance, Cuenta de Resultados, FCF, múltiplos comparativos, Piotroski Score, identificación de moat y riesgos.
- **Dependencias**: Spec 000 (Safety Guard), Spec 002 (comparte infraestructura de extracción de datos, Watchlist y caché).
- **Skill asociada**: `claude-equity-research`, `stock-info-explorer`.
- **Relación con spec 001-analisis-mercado existente**: La spec 001 actual (borrador) se subsume parcialmente aquí. Se recomienda reescribirla como Spec 003 con alcance ampliado (incluyendo Piotroski, FCF, moat), y reclasificar el borrador existente como superado.
- **Puntos críticos**: Umbrales cuantitativos del diagnóstico, gestión de entidades financieras/bancarias, disclaimer legal.

### Spec 004 — Copiloto Patrimonial (Chat Asesor)
- **Objetivo**: Asistente conversacional en Streamlit que conecta con la BD local (finanzas.db) y recomienda vehículos de inversión (cuentas remuneradas, fondos monetarios, renta variable) evaluando el saldo en "Sin Asignar" y garantizando el fondo de emergencia.
- **Dependencias**: Spec 000 (Safety Guard), Spec 003 (análisis fundamental disponible como herramienta del agente).
- **Skill asociada**: `portfolio-risk-review`, `savings-allocator`.
- **Puntos críticos**: Doble tesis obligatoria (2 riesgos bajistas mínimos por oportunidad), veto total a renta variable sin fondo cubierto, disclaimer de no-asesoramiento financiero regulado.

### Spec 005 — Infraestructura LangGraph y Orquestación de Agentes
- **Objetivo**: Grafo de estado LangGraph en el backend FastAPI que orquesta las herramientas (tools) de mercado, análisis y asignación como nodos tipados con Pydantic.
- **Dependencias**: Spec 000. Se puede desarrollar en paralelo con Specs 001-003, ya que define la infraestructura que las conecta.
- **Puntos críticos**: Definir el contrato de comunicación entre Streamlit y el grafo (ver sección 2), manejo de errores y timeouts, inyección de skills como system prompts en nodos.

> **Nota sobre el orden**: Spec 005 es transversal. Puede iniciarse tras Spec 000 y refinarse incrementalmente a medida que se completan Specs 001-004. Sin embargo, la primera spec que _necesita_ el grafo en producción es Spec 004 (Copiloto). Las Specs 001-003 pueden funcionar inicialmente con llamadas directas a servicios sin LangGraph.

---

## 2. Contratos de Comunicación

```
┌─────────────────────────────┐
│   Streamlit (Frontend)      │
│   Pestañas: Radar, Screener,│
│   Deep Dive, Copiloto       │
└──────────┬──────────────────┘
           │ HTTP (requests)
           │ api_client.py
           ▼
┌─────────────────────────────┐
│   FastAPI (Backend)         │
│   Routers existentes:       │
│     /categorias, /presupu.. │
│     /transacciones          │
│   Routers nuevos:           │
│     /market/news            │
│     /market/screener        │
│     /market/fundamental/{t} │
│     /advisor/chat           │
│     /advisor/safety-status  │
└──────────┬──────────────────┘
           │
     ┌─────┴──────┐
     │            │
     ▼            ▼
┌─────────┐  ┌──────────────────┐
│ SQLite  │  │  LangGraph Flow  │
│ local   │  │  (Spec 005)      │
│finanzas │  │                  │
│  .db    │  │  Nodos:          │
│         │  │  - news_fetcher  │
│ Tablas: │  │  - screener      │
│ categor │  │  - fundamentals  │
│ subcate │  │  - advisor       │
│ presupu │  │  - safety_guard  │
│ transac │  │                  │
│ +NUEVAS │  │  Tools:          │
│ watchl. │  │  - yfinance      │
│ cache   │  │  - news_api      │
└─────────┘  │  - sqlite_read   │
             └──────────────────┘
```

### Contratos clave:
- **Streamlit → FastAPI**: Todos los datos fluyen vía `api_client.py` existente (se extiende con nuevos métodos). Nunca acceso directo a BD desde frontend.
- **FastAPI → LangGraph**: Los endpoints nuevos invocan el grafo LangGraph como un servicio interno. El grafo recibe y devuelve schemas Pydantic tipados.
- **LangGraph → BD local**: Acceso de SOLO LECTURA a `finanzas.db` para consultar transacciones, presupuestos y fondo de emergencia. Nunca escritura desde agentes.
- **LangGraph → APIs externas**: Solo se transmiten tickers/consultas de mercado. NUNCA datos contables del usuario (Principio 6: Local Privacy).
- **Nuevas tablas SQLite**: `watchlist_items` (ticker, añadido_en, último_precio), `market_cache` (ticker, datos_json, timestamp_expiry).

---

### 3.1. Dependencias Externas

| Dependencia | Riesgo | Mitigación |
| :--- | :--- | :--- |
| **`yfinance`** | Rate limiting agresivo (sin SLA oficial), datos inconsistentes para mercados no-US, posibles cambios de API sin aviso | Caché local con TTL configurable, fallback graceful con última snapshot válida, tests con fixtures (nunca contra API real en CI) |
| **API de noticias** (por definir) | Requiere API key, posibles cuotas gratuitas limitadas | Evaluar en Spec 001: NewsAPI.org, GNews, o RSS de fuentes institucionales (BCE, Fed) sin autenticación |
| **LangGraph + Google Gemini Pro** | Requiere API key personal del usuario y gestión de cuotas de tokens | Definido proveedor oficial: Google Gemini (Plan Pro con API Key). Dependencias `langgraph`, `langchain-google-genai` en `requirements/backend.txt`. Constitución actualizada. |

### 3.2. Compatibilidad con Código Existente (Cero Regresiones)

| Riesgo | Análisis |
| :--- | :--- |
| **Migración de `financial_calculator.py`** | Actualmente en `src/frontend/services/`. Moverlo a `src/backend/` rompe los imports de `app.py`. Se necesita una fase de transición: primero mover, luego actualizar imports, luego exponer vía endpoint si es necesario. Tests antes y después. |
| **Nuevas tablas en SQLite** | `init_db()` usa `Base.metadata.create_all()`, así que los nuevos modelos se crean automáticamente sin afectar tablas existentes. Sin riesgo de regresión si los modelos nuevos no tienen FK a tablas existentes. |
| **Monolito `app.py` (678 líneas)** | Añadir 4 pestañas nuevas a un archivo de 678 líneas lo haría inmanejable. Spec 000 debería incluir la modularización del frontend en archivos por pestaña. |
| **`api_client.py` sin manejo de errores** | Los `except: pass` actuales enmascaran fallos. Los nuevos endpoints de mercado necesitan gestión de errores explícita. Esto se aborda progresivamente en cada spec. |

### 3.3. Riesgos Constitucionales

| Principio | Riesgo identificado | Estado |
| :--- | :--- | :--- |
| **P1 (Local Stack)** | Uso de LLM cloud vía Google Gemini Pro | **Resuelto**: Constitución actualizada permitiendo Google Gemini API con API key personal del usuario. |
| **P3 (Decoupled Logic)** | `financial_calculator.py` en frontend viola este principio HOY | **A abordar en Spec 000**: migración al backend y tests asociados. |
| **P5 (Safety Guard)** | Falta entidad y cálculo formal del fondo de emergencia | **A abordar en Spec 000**: creación de la entidad `EmergencyFund` en SQLite y servicio de cálculo dinámico. |
| **P4 (Veracity)** | El diagnóstico cuantitativo necesita umbrales numéricos fijos | Se estipulan umbrales objetivos y verificables en tests para Spec 003. |

---

## 4. Resoluciones y Acuerdos Arquitectónicos

1. **Proveedor LLM**: Confirmado **Google Gemini (Plan Pro)** consumido mediante la API oficial (`google-genai` / `langchain-google-genai`) con API Key personal del usuario. Constitución modificada para formalizar la excepción manteniendo la privacidad de datos contables locales.
2. **Entidad y Lógica del Fondo de Emergencia**: Se integrará en la base de datos como entidad formal (`EmergencyFund`). La subcategoría "Fondo de emergencia" es el flujo mensual de aportación (debe ser 0 € si el fondo está completo). Si el coste de Necesidades Básicas aumenta, la meta sube dinámicamente, pasando a requerir aportaciones de nuevo en los meses sucesivos hasta restaurar la cobertura completa.
3. **Universo del Screener**: Se aplaza la decisión sobre tickers fijos o libres para definirse detalladamente en la redacción de la **Spec 002**.
4. **Destino del Borrador Spec 001**: El borrador actual de `specs/001-analisis-mercado/spec.md` se archiva/sustituye y su alcance se redactará como la **Spec 003 (Deep Dive & Análisis Fundamental)** ampliada.
5. **API de Noticias**: Se evaluará en la **Spec 001** (Radar Macro y Noticias) entre proveedores gratuitos y RSS institucionales.
