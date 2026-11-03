import asyncio
from contextlib import asynccontextmanager
import logging
import os
import time
from fastapi import FastAPI, Request
from backend.utils.logging_config import setup_logging
from backend.api.routers import (
    categories,
    budgets,
    transactions,
    safety_guard,
    market,
    screener,
    deepdive,
    watchlist,
    copilot,
    committee,
    guidelines,
    metrics,
    joint,
    backup,
    updater,
)
from backend.database.componentes.sqlite_db import SessionLocal, init_db
from backend.services import backup_service

# Configurar logging persistente rotativo con filtro de privacidad
backend_log_file = os.getenv("BACKEND_LOG_FILE", "logs/backend.log")
setup_logging(backend_log_file)
logger = logging.getLogger("backend.api.main")
logger.info("Inicializando servicio Backend FastAPI y base de datos")

# Inicializar la base de datos
init_db()


async def run_periodic_backup_checker():
    """Worker no bloqueante que evalúa periódicamente (cada 1h) respaldos programados."""
    while True:
        try:
            await asyncio.sleep(3600)
            db = SessionLocal()
            try:
                backup_service.check_and_run_scheduled_backup(db)
            finally:
                db.close()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Error en verificación periódica de copias de seguridad: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación con comprobación inicial y worker de copias en background."""
    try:
        db = SessionLocal()
        try:
            backup_service.check_and_run_scheduled_backup(db)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Fallo al comprobar copias programadas en arranque: %s", exc)

    worker_task = asyncio.create_task(run_periodic_backup_checker())
    yield
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Gestor Finanzas API", lifespan=lifespan)



@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """Middleware de observabilidad para registrar método, ruta, código HTTP y latencia."""
    start_time = time.perf_counter()
    method = request.method
    query = request.url.query
    path_with_query = f"{request.url.path}?{query}" if query else request.url.path

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            "HTTP %s %s completed with status %d in %.2f ms",
            method,
            path_with_query,
            response.status_code,
            duration_ms,
        )
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        logger.error(
            "HTTP %s %s failed with exception: %s after %.2f ms",
            method,
            path_with_query,
            str(exc),
            duration_ms,
        )
        raise

# Routers principales en estándar internacional
app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(transactions.router)
app.include_router(safety_guard.router)
app.include_router(market.router)
app.include_router(screener.router)
app.include_router(deepdive.router)
app.include_router(watchlist.router)
app.include_router(copilot.router)
app.include_router(committee.router)
app.include_router(guidelines.router)
app.include_router(metrics.router)
app.include_router(joint.router)
app.include_router(backup.router)
app.include_router(updater.router)



@app.get("/")
def read_root():
    return {"message": "Gestor Finanzas API funcionando"}

