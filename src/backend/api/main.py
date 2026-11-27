import asyncio
from contextlib import asynccontextmanager
import logging
import os
import re
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.utils.env_setup import ensure_env_file
from backend.utils.logging_config import setup_logging
from backend.init_db_data import populate

# Asegurar entorno local .env antes de inicializar logging
ensure_env_file()
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
    mobile,
)
from backend.database.componentes.sqlite_db import SessionLocal, init_db
from backend.services import backup_service
from backend.services.mobile_sync_service import MobileSyncService
from fastapi.staticfiles import StaticFiles

# Configurar logging persistente rotativo con filtro de privacidad
backend_log_file = os.getenv("BACKEND_LOG_FILE", "logs/backend.log")
setup_logging(backend_log_file)
logger = logging.getLogger("backend.api.main")
logger.info("Inicializando servicio Backend FastAPI y base de datos")

# Inicializar la base de datos y catálogo estándar inicial de forma idempotente
init_db()
populate()


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


async def run_periodic_mobile_sync_checker():
    """Worker no bloqueante que evalúa periódicamente (cada 30s) el buzón móvil."""
    while True:
        try:
            await asyncio.sleep(30)
            sync_service = MobileSyncService()
            # Optimización de I/O: verificar archivos en disco antes de instanciar sesión en SQLite
            has_pending = (
                sync_service.inbox_dir.exists()
                and any(
                    f.is_file() and not f.name.startswith(".") and f.suffix.lower() == ".json"
                    for f in sync_service.inbox_dir.iterdir()
                )
            )
            if has_pending:
                db = SessionLocal()
                try:
                    sync_service.process_mobile_inbox_folder(db)
                finally:
                    db.close()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Error en verificación periódica de sincronización móvil: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación con comprobación inicial y workers en background."""
    try:
        db = SessionLocal()
        try:
            backup_service.check_and_run_scheduled_backup(db)
            sync_service = MobileSyncService()
            sync_service.process_mobile_inbox_folder(db)
            sync_service.export_catalog_file(db)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Fallo al ejecutar comprobaciones iniciales en arranque: %s", exc)

    backup_task = asyncio.create_task(run_periodic_backup_checker())
    mobile_task = asyncio.create_task(run_periodic_mobile_sync_checker())
    yield
    backup_task.cancel()
    mobile_task.cancel()
    try:
        await asyncio.gather(backup_task, mobile_task, return_exceptions=True)
    except Exception:
        pass


app = FastAPI(title="Gestor Finanzas API", lifespan=lifespan)

# Soporte integral de CORS para clientes móviles (autenticación por cabecera X-Mobile-Pairing-Token, sin cookies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PROXY_CONFINEMENT_HEADERS = (
    "x-forwarded-for",
    "forwarded",
    "x-real-ip",
    "tailscale-user-login",
    "tailscale-user-name",
)
_SENSITIVE_QUERY_PATTERN = re.compile(r"(?i)(^|&)(token|pin)=[^&]*")


@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    """Middleware de seguridad proxy (confinamiento móvil) y observabilidad con sanitización."""
    start_time = time.perf_counter()
    method = request.method
    query = request.url.query
    safe_query = _SENSITIVE_QUERY_PATTERN.sub(r"\1\2=[REDACTED]", query) if query else ""
    path_with_query = f"{request.url.path}?{safe_query}" if safe_query else request.url.path

    # Si la petición entra a través de proxy inverso (ej. Tailscale Serve), confinar solo a rutas móviles
    if method != "OPTIONS" and any(request.headers.get(h, "").strip() for h in _PROXY_CONFINEMENT_HEADERS):
        req_path = request.url.path
        if not (
            req_path == "/mobile"
            or req_path.startswith("/mobile/")
            or req_path.startswith("/api/mobile/")
        ):
            logger.warning("Acceso denegado por proxy a ruta no móvil: %s %s", method, path_with_query)
            return JSONResponse(
                status_code=403,
                content={"detail": "Acceso denegado: el túnel remoto solo permite rutas móviles."},
            )

    try:
        response = await call_next(request)
        if request.url.path.startswith("/mobile") and (
            request.url.path in ("/mobile", "/mobile/")
            or request.url.path.endswith((".html", ".js", "manifest.json"))
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
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
app.include_router(mobile.router)

# Montaje de la aplicación móvil estática (PWA)
mobile_dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mobile", "dist")
os.makedirs(mobile_dist_dir, exist_ok=True)
placeholder_index = os.path.join(mobile_dist_dir, "index.html")
if not os.path.exists(placeholder_index):
    with open(placeholder_index, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><head><title>Gestor Finanzas Mobile</title></head><body><h1>Gestor Finanzas Quick-Capture</h1></body></html>")
app.mount("/mobile", StaticFiles(directory=mobile_dist_dir, html=True), name="mobile_pwa")


@app.get("/")
def read_root():
    return {"message": "Gestor Finanzas API funcionando"}

