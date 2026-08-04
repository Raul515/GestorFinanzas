# Gestor de Finanzas Personales

Un gestor de finanzas automatizado local, utilizando FastAPI y Streamlit.
La base de datos (SQLite) se almacena localmente y no se sube a GitHub gracias al `.gitignore`.

## Arquitectura

- **Backend (API):** FastAPI + SQLAlchemy + Pydantic. Estructurado en capas (Domain, Database, API).
- **Frontend (UI):** Streamlit.
- **Base de Datos:** SQLite (`src/backend/data/finanzas.db`).

## Ejecución con Docker Compose

La forma recomendada de levantar la aplicación es mediante Docker.

1. Ve a la carpeta `docker_local`:
```bash
cd docker_local
```

2. Ejecuta el entorno base (o de desarrollo si quieres recarga automática):

**Entorno de Producción/Base:**
```bash
docker compose up --build
```

**Entorno de Desarrollo (Hot Reload):**
```bash
docker compose -f docker-compose.yml -f docker-compose.extend.yml up --build
```

La web estará disponible en `http://localhost:8501`.

## Inicializar Datos

Si tu base de datos está vacía, puedes popularla con las categorías de tu Excel entrando al contenedor del backend:
```bash
docker exec -it backend_gestor python src/backend/init_db_data.py
```
