from fastapi import FastAPI
from backend.api.routers import categories, budgets, transactions, safety_guard, market, screener
from backend.database.componentes.sqlite_db import init_db

app = FastAPI(title="Gestor Finanzas API")

# Inicializar la base de datos
init_db()

# Routers principales en estándar internacional
app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(transactions.router)
app.include_router(safety_guard.router)
app.include_router(market.router)
app.include_router(screener.router)



@app.get("/")
def read_root():
    return {"message": "Gestor Finanzas API funcionando"}

