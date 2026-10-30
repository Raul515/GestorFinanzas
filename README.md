# 💰 Gestor de Finanzas Personales y Comité Asesor Agéntico

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/Multiagent-LangGraph-FF6F00.svg)](https://langchain-ai.github.io/langgraph/)
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini%20Pro-4285F4.svg?logo=google&logoColor=white)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20Local-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-276%2F276%20Passed-brightgreen.svg)]()
[![Type Checking](https://img.shields.io/badge/Pyright-0%20Errors-brightgreen.svg)]()

Un sistema integral, local y privado de **Gestión de Finanzas Personales y Asesoramiento Patrimonial Multiagente**, diseñado para el control presupuestario bajo la **metodología 50/30/20**, el blindaje patrimonial estricto mediante **salvaguarda de seguridad** (Principio 9 de la Constitución) y la deliberación de oportunidades de inversión orquestada con **LangGraph** y **Google Gemini Pro**.

---

## 🏛️ Filosofía y Gobernanza (Spec-Driven Development)

El proyecto se rige por la metodología **Desarrollo Guiado por Especificaciones (Spec-Driven Development - SDD)** en modo anclado a especificaciones, bajo los 13 principios innegociables de la [Constitución del Proyecto](docs/constitution.md):

1. **Privacidad y Soberanía de Datos (Principio 10)**: La contabilidad, transacciones y sesiones residen en SQLite local (`finanzas.db`). Ningún dato privado se expone en prompts a modelos de IA; sólo métricas cuantitativas agregadas y neutrales calculadas previamente en Python.
2. **Salvaguarda de Seguridad y Veto Innegociable (Principio 9)**: Si el Fondo de Emergencia cubre `< 3 meses` de necesidades básicas, el sistema levanta de forma determinista un **veto constitucional**, bloqueando cualquier recomendación o compra de renta variable y reorientando el capital a liquidez.
3. **Auditoría de Doble Tesis (Principio 12)**: Prohibido emitir tesis alcistas aisladas. Todo análisis de activos exige la formulación obligatoria de al menos **dos riesgos bajistas severos** (*¿Qué puede salir mal y cuánto beneficio destruiría?*).
4. **Observabilidad y Prohibición de Fallos Silenciosos (Principio 13)**: Prohibido silenciar excepciones con `pass`. Todo error de red o de ejecución se registra en logs estructurados con niveles adecuados.
5. **Estándar Internacional de Nomenclatura (Opción 1)**: Código backend, esquemas Pydantic, base de datos SQLite y endpoints REST 100% en inglés. Interfaz gráfica (Streamlit), documentación y reportes 100% en español.

---

## 🚀 Módulos y Capacidades del Sistema

### 1. 📊 Presupuesto 50/30/20 y Fondo "Sin Asignar"
- **Regla 50/30/20 Dinámica**: Clasificación matemática en *Necesidades Básicas* (50%), *Deseos* (30%) y *Ahorro e Inversión* (20%).
- **Sector Neutro "Sin Asignar"**: Computa el excedente de ingresos reales no comprometidos en el mes, disponible para asignación estratégica o ahorro.
- **Resumen Anual y Mensual**: Cuadros de flujo, desvíos porcentuales, evolución del ahorro y gráficos comparativos interactivos con Altair.
- **Presupuesto Base**: Plantilla maestra editable para replicar presupuestos mensuales.

### 2. 🛡️ Salvaguarda de Seguridad (Safety Guard)
- **Fondo de Emergencia Dinámico**: Modelo SQLite `EmergencyFund` con cálculo automático de meta (`monthly_needs * 3`). Si los gastos esenciales crecen, la meta se ajusta automáticamente.
- **Semáforo Patrimonial**: Muestra meses reales cubiertos, brecha financiera y estado de habilitación para inversión.

### 3. 🌐 Radar Macroeconómico y Noticias Financieras
- **Indicadores Clave**: Seguimiento automático de índices (IBEX 35, EuroStoxx 50, S&P 500, Nasdaq 100) y rendimientos de deuda soberana (Bono España 10A, Bund Alemán 10A y Bono US 10A).
- **Prima de Riesgo en Vivo**: Cálculo diferencial en puntos básicos entre el bono español y el alemán vía API SDMX del Banco Central Europeo (BCE).
- **Agregador RSS y Yahoo Finance**: Fuentes públicas depuradas (elEconomista, Cinco Días, BCE, Yahoo Finance).
- **Análisis de Impacto con Google Gemini**: Clasificación neutral de relevancia (Alta, Media, Baja), sector y síntesis objetiva sin sensacionalismo.
- **Caché SQLite de 24 horas**: Modelo `MarketCache` para evitar llamadas redundantes a APIs externas.

### 4. 🔍 Screener Fundamental y Universos Modulares
- **Universos Bajo Demanda**: IBEX 35, EuroStoxx 50, S&P 500 Top 50, ETFs UCITS de bajas comisiones y lista de tickers personalizados (hasta 50).
- **Múltiplos Contables**: PER, Shiller PE (CAPE), Dividend Yield, ROE, Deuda Neta/EBITDA, Debt/Equity y Expense Ratio.
- **Presets Estratégicos**: *Calidad (Compounders)*, *Alto Dividendo Sostenible*, *Value Investing*, *Crecimiento a Precio Razonable (GARP)* y *ETFs Bajo Coste*.
- **Cero Consumo de Tokens de IA**: Filtrado puramente cuantitativo y persistencia de 24 horas en caché local.

### 5. 🔬 Análisis Fundamental Deep Dive & Quality Value
- **Auditoría Contable a 4 Años**: Extracción histórica de Balance, Cuenta de Resultados y Estado de Flujos de Caja.
- **Piotroski F-Score (0 a 9 puntos)**: Algoritmo determinista puro evaluando Rentabilidad, Apalancamiento/Liquidez y Eficiencia Operativa (con adaptación contable a 7 puntos para banca).
- **Métricas de Caja Libre (FCF)**: FCF Yield, tasa de conversión EBITDA-to-FCF, intensidad CapEx y diagnóstico de foso defensivo (*Moat*).
- **Tesis Agéntica Quality Value**: Matriz en tres cuadrantes (*Calidad y Valor*, *Calidad Cara*, *Trampa de Valor*), matriz de riesgos "¿Qué puede salir mal?" y proyección de valoración a 5 años con TIR exigida del 15%-20%.
- **Lista de Seguimiento (Watchlist)**: Registro local persistente en SQLite para monitorizar empresas objetivo con precio y notas.

### 6. 💬 Copiloto Patrimonial (Function Calling & Asistente Conversacional)
- **Bucle de Function Calling Nativo**: Asistente con Google Gemini Pro que invoca herramientas bajo demanda (`get_financial_profile`, `get_watchlist_items`, `get_cached_deepdive`, `get_cached_macro_overview`, `search_local_knowledge`).
- **Persistencia de Sesiones**: Tablas SQLite `copilot_sessions` y `copilot_messages` con auto-generación de títulos, historial cronológico y borrado en cascada.
- **Veto Vinculante y Doble Tesis**: Rechazo automático a recomendar renta variable si el fondo es menor a 3 meses, y formulación obligatoria de riesgos bajistas.

### 7. 🏛️ Comité Asesor de Inversión Multiagente (LangGraph)
Orquestación colegiada mediante un grafo de estados (`StateGraph`) con cinco agentes especializados:
1. 🛡️ **`SafetyGuardAgent`**: Valida deterministamente la liquidez y aplica el cortocircuito condicional si la salvaguarda no está superada.
2. 🌐 **`MacroAgent`**: Audita tipos del BCE, rendimientos soberanos y primas de riesgo.
3. 🔬 **`FundamentalAgent`**: Analiza estados financieros a 4 años, Piotroski Score y elabora la tesis favorable (Bull Case).
4. 🐻 **`RiskThesisAgent` (Red Team)**: Exige y formula al menos **dos riesgos bajistas severos** (Principio 12).
5. ⚖️ **`PortfolioAdvisorAgent` (Supervisor)**: Emite el veredicto final vinculante, plan de despliegue de liquidez por tramos (Tramo Inicial, Acumulación y Colchón de Reserva) y zona de entrada por TIR.

### 8. 📋 Historial y Gestión Segura de Transacciones (Spec 006)
- **Eliminación Segura Interactiva**: Confirmación visual en dos pasos con `st.popover` para prevenir borrados accidentales de apuntes contables.
- **Sincronización Automática del Fondo de Emergencia**: Si se elimina una transacción que aportaba al Fondo de Emergencia, su saldo acumulado se resta automáticamente para evitar descuadres.
- **Reversión en Cascada de Estrategias**: Si una transacción proviene de una estrategia de pautas, el sistema identifica su vinculación (`applied_strategy_id`), revierte todas las transacciones asociadas del lote y reabre la disponibilidad del capital.
- **Usabilidad y Formato Estándar**: Formato de fecha en estándar español `DD/MM/AAAA` y reseteo selectivo inteligente de campos (concepto a blanco y cantidad a 0, preservando fecha y subcategoría para inserciones ágiles).

### 9. 📜 Sistema de Logs Rotativos Persistentes y Observabilidad (Spec 007)
- **Rotación Automática en Disco**: Archivos independientes `logs/backend.log` y `logs/frontend.log` limitados a 5 MB con hasta 3 copias de seguridad rotativas, protegiendo el almacenamiento local.
- **Middleware de Latencia en FastAPI**: Registro estructurado de tiempos de procesamiento de cada petición HTTP en milisegundos y exposición en el encabezado `X-Process-Time`.
- **Filtro Criptográfico de Privacidad (`PrivacyFilter`)**: Sanitización activa e irreversible de claves API de Google Gemini (`AIza...`), tokens Bearer y credenciales antes de ser emitidos a los ficheros de log o la consola.

### 10. 💡 Pautas Deterministas de Gestión y Compensación Presupuestaria (Spec 008)
- **Motor Cuantitativo Determinista Puro**: Diagnóstico financiero matemático en tiempo real (0% consumo de LLM, latencia cero) evaluando desviaciones presupuestarias sobre la regla 50/30/20 y desglosando cifras reales en euros.
- **6 Escenarios Mensuales y Diagnóstico Estructural Anual**:
  - *Superávit en Necesidades Básicas*: Activación de estrategias de aceleración de capital (FIRE, Sinking Fund o Enfoque Híbrido 80/20).
  - *Déficit en Necesidades Básicas*: Jerarquía de compensación presupuestaria en tres líneas de defensa y amortiguación directa desde Deseos sin tocar el Fondo de Emergencia.
  - *Exceso en Deseos*: Veto estricto al Fondo de Emergencia y programación interactiva de ajustes compensatorios para el mes siguiente.
  - *Caída de Ingresos Netos*: Protocolo de contención patrimonial y congelación de partidas de estilo de vida a 0.00 €.
  - *Ingreso Extraordinario (Bonus / Paga Extra)*: Inyección prioritaria a completar los 3 meses de fondo o asignación equilibrada 80% inversión / 20% disfrute.
  - *Dinero Sin Asignar Elevado*: Canalización de liquidez ociosa acumulada en cuenta corriente.
  - *Diagnóstico Anual*: Evaluación consolidada de rigidez de costes fijos, lifestyle creep y tasa de ahorro global.
- **Colchón Prudencial y Asignación Atómica**: Selección flexible de despliegue al 100% o 50% con colchón preventivo dentro de Necesidades. Registro en `AppliedGuidelineStrategy` e inserción en el historial como transacciones reales.
- **Barrido Inteligente de Cierre de Mes (Día >= 26)**: Liquidación del remanente heredando las proporciones de la estrategia activa (`INHERIT_STRATEGY`) o canalización tradicional hacia el ahorro (`DEFAULT_SAVINGS`).
- **Botón `↩️ Deshacer Estrategia` con Popover de Confirmación**: Permite anular atómicamente la estrategia ejecutada, eliminando transacciones vinculadas y restaurando saldos.
- **Detección Elegante de Meses y Años Vacíos**: Presentación limpia con estado *"Mes/Año sin Información Financiera"* en períodos sin transacciones ni presupuestos, evitando falsas felicitaciones o tablas engañosas.

---

## 🛠️ Arquitectura y Tecnologías

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Streamlit)                            │
│  • Pestañas: 50/30/20, Radar Macro, Screener, Deep Dive, Copiloto,      │
│              Comité Asesor, Pautas Deterministas, Historial            │
│  • Visualizaciones: Altair (Sparklines, Barras, Donut 50/30/20)        │
│  • Estilos: CSS Modular (Light / Dark Mode Nativo)                     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST (api_client.py)
┌───────────────────────────────────▼────────────────────────────────────┐
│                         BACKEND (FastAPI)                              │
│  • API Routers: /categories, /budgets, /transactions, /safety-guard,   │
│                 /market, /screener, /deepdive, /watchlist, /copilot,   │
│                 /committee, /guidelines                                │
│  • Middleware: Latencia y Observabilidad (X-Process-Time)              │
│  • Motor Cognitivo LangGraph: StateGraph, Reducers, Cond. Edges        │
│  • Agentes: BaseAgent (Safety, Macro, Fundamental, Risk, Advisor)      │
│  • Modelos LLM: Google Gemini Pro (google-genai SDK)                   │
│  • Servicios Puros: financial_calculator, safety_guard, market_data,    │
│                     equity_deepdive, screener_service, guidelines      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ SQLAlchemy 2.0 ORM
┌───────────────────────────────────▼────────────────────────────────────┐
│                   PERSISTENCIA LOCAL (SQLite)                          │
│  • src/backend/data/finanzas.db (100% privado en tu equipo)            │
│  • Tablas: categories, subcategories, budgets, transactions,           │
│            emergency_funds, market_cache, watchlist, copilot_sessions, │
│            copilot_messages, applied_guideline_strategies              │
└────────────────────────────────────────────────────────────────────────┘
```

- **Backend**: Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, LangGraph, LangChain Core, Google GenAI SDK (`google-genai`), yfinance, feedparser.
- **Frontend**: Streamlit, Altair, Pandas, Requests.
- **Logging & Observabilidad**: Logging rotativo persistente (5 MB, 3 backups) y filtro de sanitización criptográfica (`PrivacyFilter`).
- **Testing y Calidad**: Pytest (276 pruebas pasando al 100%), Pyright (0 errores), Compileall.
- **Contenedores**: Docker & Docker Compose local.

---

## 📁 Estructura del Proyecto

```text
GestorFinanzas/
├── AGENTS.md                  # Directrices operativas y gobernanza de agentes IA
├── MEMORY.md                  # Memoria persistente del proyecto y registro de decisiones
├── pyproject.toml / pytest.ini # Configuración de herramientas y suite de pruebas
├── pyrightconfig.json         # Configuración del analizador estático Pyright
├── README.md                  # Documentación global del proyecto
├── docker_local/              # Configuración local de Docker Compose
│   ├── docker-compose.yml
│   └── docker-compose.extend.yml
├── docs/                      # Documentación constitucional y metodológica
│   └── constitution.md        # Ley Suprema: Los 13 Principios Innegociables
├── logs/                      # Logs rotativos del sistema (sanitizados con PrivacyFilter)
│   ├── backend.log
│   └── frontend.log
├── requirements/              # Requisitos de dependencias desacoplados
│   ├── backend.txt
│   └── frontend.txt
├── specs/                     # Especificaciones de desarrollo (SDD)
│   ├── README.md              # Índice de especificaciones
│   ├── 000-architecture-map/ # Mapa de arquitectura inicial
│   ├── 000-cimientos-safety-guard/
│   ├── 001-radar-macro-noticias/
│   ├── 002-screener-oportunidades/
│   ├── 003-analisis-fundamental/
│   ├── 004-copiloto-patrimonial/
│   ├── 005-orquestacion-langgraph/
│   ├── 006-gestion-transacciones/
│   ├── 007-sistema-logs-rotativos/
│   └── 008-pautas-gestion-determinista/
├── src/
│   ├── backend/               # Servidor FastAPI y arquitectura cognitiva
│   │   ├── agents/            # Motor Cognitivo: Especializaciones de BaseAgent
│   │   ├── api/               # Servidor REST y routers (/guidelines, /committee...)
│   │   ├── components/        # Nodos LangGraph, orquestador y herramientas
│   │   ├── database/          # Persistencia SQLite (patrón Repositorio y migraciones)
│   │   ├── domain/            # Modelos ORM, esquemas Pydantic y estados de agentes
│   │   └── services/          # Lógica financiera pura (guidelines, safety_guard, screener...)
│   └── frontend/              # Aplicación web Streamlit
│       ├── api_client.py      # Cliente HTTP estructurado con observabilidad
│       ├── app.py             # Interfaz de usuario interactiva
│       ├── services/          # Componentes de presentación visual (guidelines_view)
│       └── style.css          # Sistema de diseño y estilos CSS
└── tests/                     # Suite de pruebas automatizadas (276 pruebas)
    ├── conftest.py            # Fixtures de base de datos SQLite en memoria
    ├── integration/           # Pruebas de integración de endpoints REST
    └── unit/                  # Pruebas unitarias de servicios, schemas y vistas
```

---

## 📦 Instalación y Puesta en Marcha

### Requisitos Previos
- Python 3.11 instalado.
- Git instalado.
- *(Opcional)* Clave de API de Google Gemini (`GEMINI_API_KEY`) para las síntesis cualitativas y el Copiloto/Comité (los cálculos matemáticos contables son 100% locales y deterministas).

---

### Opción 1: Ejecución Local en Entorno Virtual (Oficial)

1. **Clonar el repositorio**:
   ```powershell
   git clone https://github.com/Raul515/GestorFinanzas.git
   cd GestorFinanzas
   ```

2. **Crear y activar el entorno virtual (`venv`)**:
   ```powershell
   # En Windows PowerShell:
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # En Linux / macOS:
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias**:
   ```powershell
   pip install -r requirements/backend.txt
   pip install -r requirements/frontend.txt
   ```

4. **Configurar variables de entorno**:
   Copia el archivo de plantilla `.env.example` a `.env` (registrado en `.gitignore`):
   ```powershell
   cp .env.example .env
   ```
   Edita `.env` con tu clave:
   ```env
   GEMINI_API_KEY="tu_clave_de_gemini_aqui"
   GEMINI_MODEL="gemini-2.5-pro"
   ```

5. **Inicializar la base de datos local**:
   ```powershell
   $env:PYTHONPATH="src"
   .\venv\Scripts\python src/backend/init_db_data.py
   ```

6. **Iniciar el Backend (FastAPI)**:
   ```powershell
   $env:PYTHONPATH="src"
   .\venv\Scripts\uvicorn backend.api.main:app --reload --port 8000
   ```

7. **Iniciar el Frontend (Streamlit)** (en otra terminal con `venv` activo):
   ```powershell
   $env:PYTHONPATH="src"
   .\venv\Scripts\streamlit run src/frontend/app.py
   ```
   Abre tu navegador en: **`http://localhost:8501`** (Documentación interactiva de la API en `http://localhost:8000/docs`).

---

### Opción 2: Con Docker Compose

1. Dirígete a la carpeta `docker_local`:
   ```bash
   cd docker_local
   ```
2. Levanta los contenedores con recarga automática:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.extend.yml up --build
   ```
3. Accede a Streamlit en **`http://localhost:8501`**.

---

## 🧪 Verificación y Suite de Pruebas

El repositorio cuenta con una cobertura integral de pruebas deterministas e integración continua local:

- **Ejecutar la suite completa de pruebas (276 pruebas)**:
  ```powershell
  .\venv\Scripts\pytest -v
  ```
- **Comprobación de tipado estático (Pyright)**:
  ```powershell
  npx pyright src tests
  ```
- **Verificación de sintaxis Python**:
  ```powershell
  .\venv\Scripts\python -m compileall src tests
  ```

---

## ⚖️ Descargo de Responsabilidad (Legal Disclaimer)

Este software ha sido diseñado con fines exclusivamente **educativos, formativos y de organización financiera personal**. Ni los cálculos de ratios contables, ni las alertas de salvaguarda, ni las síntesis generadas por los modelos de lenguaje (Google Gemini) o el Comité Asesor Multiagente (LangGraph) constituyen asesoramiento financiero regulado bajo la normativa **MiFID II** o recomendaciones de inversión vinculantes emitidas por entidades supervisadas (CNMV / SEC). 

Toda inversión en activos financieros conlleva riesgo de pérdida parcial o total del capital. El usuario es el único y exclusivo responsable de sus decisiones patrimoniales.

---

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.