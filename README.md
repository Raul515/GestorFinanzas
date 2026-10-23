# 💰 Gestor de Finanzas Personales Automatizado

Un gestor de finanzas personales automatizado y local, diseñado para un control preciso de ingresos, gastos y ahorro basado en la **metodología de presupuesto 50/30/20** (50% Necesidades Básicas, 30% Deseos y 20% Ahorro e Inversión).

El proyecto está construido con una arquitectura moderna desacoplada en capas (FastAPI en el backend y Streamlit en el frontend), persistiendo los datos en una base de datos local SQLite.

---

## 🚀 Características Principales

- 📊 **Resumen Anual Consolidado**:
  - Tabla de flujo dinámico con cálculo de desvíos en porcentaje sobre ingresos netos reales.
  - Gráficos comparativos de gasto/ahorro mensual y evolución del ahorro acumulado.
- 📅 **Gestión Detallada por Mes**:
  - Resumen KPI mensual de Ingresos, Gastos Totales y Balance Neto de Ahorro.
  - Gráficos comparativos por categoría (Presupuesto vs. Real).
  - Tablas desglosadas por subcategorías con cálculo de desviaciones.
- 🍰 **Análisis 50/30/20 & Bloque "Sin Asignar"**:
  - Gráfico circular ajustado exactamente sobre los **Ingresos Reales del mes**.
  - Sector neutro **Sin Asignar** que representa el saldo de ingresos disponible no ejecutado ni comprometido.
  - Tarjetas de cumplimiento objetivo frente a las metas 50/30/20.
- ➕ **Registro de Transacciones**:
  - Formulario intuitivo para registrar gastos e ingresos asociados a fecha, categoría y subcategoría.
- ⚙️ **Presupuesto Base (Plantilla Maestro)**:
  - Definición de presupuestos por defecto y posibilidad de personalizar meses concretos de forma independiente.

---

## 🛠️ Arquitectura y Tecnologías

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) + [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (Modelos fuertemente tipados con `Mapped` y `mapped_column`) + [Pydantic](https://docs.pydantic.dev/).
- **Frontend**: [Streamlit](https://streamlit.io/) + [Altair](https://altair-viz.github.io/) (Gráficos interactivos).
- **Base de Datos**: SQLite local almacenada en `src/backend/data/finanzas.db` (excluida del control de versiones por seguridad).
- **Despliegue / Contenedores**: Docker & Docker Compose.

---

## 📁 Estructura del Proyecto

```text
GestorFinanzas/
├── docker_local/              # Configuración y orquestación de Docker Compose
│   ├── docker-compose.yml
│   └── docker-compose.extend.yml (Desarrollo con Hot-Reload)
├── images/                    # Dockerfiles del frontend y backend
│   ├── backend/Dockerfile
│   └── frontend/Dockerfile
├── requirements/              # Dependencias de Python
│   ├── backend.txt
│   └── frontend.txt
├── src/
│   ├── backend/               # Servidor FastAPI y capa de persistencia
│   │   ├── api/               # Endpoints REST
│   │   ├── database/          # Conexión SQLite y Repositorio CRUD
│   │   ├── domain/            # Modelos de SQLAlchemy y Schemas Pydantic
│   │   └── init_db_data.py   # Script de población inicial
│   └── frontend/              # Aplicación web interactiva Streamlit
│       ├── api_client.py      # Cliente HTTP para comunicarse con el Backend
│       ├── app.py             # Interfaz de usuario principal
│       └── style.css          # Estilos CSS personalizados
├── pyrightconfig.json         # Configuración del linter estático Pyright
└── README.md
```

---

## 📦 Instalación y Ejecución

### Opción 1: Con Docker Compose (Recomendado)

1. Dirígete a la carpeta `docker_local`:
   ```bash
   cd docker_local
   ```

2. Levanta el entorno de **Desarrollo (con recarga automática)**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.extend.yml up --build
   ```

   O para el entorno de **Producción**:
   ```bash
   docker compose up --build
   ```

3. Abre el navegador e ingresa a: **`http://localhost:8501`**

---

### Opción 2: Ejecución Local en Entorno Virtual

1. Crear y activar el entorno virtual de Python:
   ```bash
   python -m venv venv
   .\venv\Scripts\Activate.ps1  # Windows PowerShell
   # source venv/bin/activate   # Linux/macOS
   ```

2. Instalar dependencias:
   ```bash
   pip install -r requirements/backend.txt
   pip install -r requirements/frontend.txt
   ```

3. Poblar la base de datos con las categorías iniciales (si está vacía):
   ```bash
   $env:PYTHONPATH="src"
   python src/backend/init_db_data.py
   ```

4. Iniciar el Backend (FastAPI):
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

5. Iniciar el Frontend (Streamlit) en otra terminal:
   ```bash
   streamlit run src/frontend/app.py
   ```

---

## 🌱 Población Inicial de Datos

Si la base de datos es nueva o deseas inicializar la estructura por defecto:
```bash
docker exec -it backend_gestor python src/backend/init_db_data.py
```

---

## 🔮 Próximos Pasos & Roadmap

- 👥 **Soporte Multiusuario**: Gestión de perfiles individuales (ej. soporte para 2 o más usuarios).
- 🤝 **Gastos Compartidos**: Reparto de gastos comunes (50/50, proporcionales por sueldo o personalizados).
- 🏦 **Cuentas Conjuntas vs. Personales**: Separación clara entre finanzas personales y fondo/cuenta común.