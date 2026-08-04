from fastapi import FastAPI
from backend.api.routers import categorias, presupuestos, transacciones
from backend.database.componentes.sqlite_db import init_db

app = FastAPI(title="Gestor Finanzas API")

# Initialize database
init_db()

# Include routers
app.include_router(categorias.router)
app.include_router(presupuestos.router)
app.include_router(transacciones.router)

@app.get("/")
def read_root():
    return {"message": "Gestor Finanzas API funcionando"}
