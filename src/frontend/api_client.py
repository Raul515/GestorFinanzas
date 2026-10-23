import requests
import os

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")


def get_categorias():
    """Obtiene el listado de categorías, normalizando claves para compatibilidad."""
    try:
        response = requests.get(f"{API_URL}/categories/")
        if response.status_code == 200:
            raw = response.json()
            for c in raw:
                if "name" in c and "nombre" not in c:
                    c["nombre"] = c["name"]
                if "type" in c and "tipo" not in c:
                    c["tipo"] = c["type"]
            return raw
    except Exception:
        pass
    return []


def get_subcategorias(categoria_id=None):
    """Obtiene subcategorías, normalizando claves para compatibilidad."""
    params = {}
    if categoria_id:
        params["category_id"] = categoria_id
    try:
        response = requests.get(f"{API_URL}/categories/subcategories/", params=params)
        if response.status_code == 200:
            raw = response.json()
            for s in raw:
                if "name" in s and "nombre" not in s:
                    s["nombre"] = s["name"]
            return raw
    except Exception:
        pass
    return []


def get_presupuestos(mes):
    """Obtiene presupuestos de un mes, normalizando claves para compatibilidad."""
    try:
        response = requests.get(f"{API_URL}/budgets/{mes}")
        if response.status_code == 200:
            raw = response.json()
            for p in raw:
                if "month" in p and "mes" not in p:
                    p["mes"] = p["month"]
                if "amount" in p and "cantidad" not in p:
                    p["cantidad"] = p["amount"]
            return raw
    except Exception:
        pass
    return []


def get_transacciones(mes=None):
    """Obtiene transacciones de un mes, normalizando claves para compatibilidad."""
    params = {}
    if mes:
        params["month"] = mes
    try:
        response = requests.get(f"{API_URL}/transactions/", params=params)
        if response.status_code == 200:
            raw = response.json()
            for t in raw:
                if "date" in t and "fecha" not in t:
                    t["fecha"] = t["date"]
                if "amount" in t and "cantidad" not in t:
                    t["cantidad"] = t["amount"]
                if "description" in t and "concepto" not in t:
                    t["concepto"] = t["description"]
            return raw
    except Exception:
        pass
    return []


def create_transaccion(fecha, subcategoria_id, cantidad, concepto):
    data = {
        "date": fecha.isoformat() if hasattr(fecha, "isoformat") else str(fecha),
        "subcategory_id": subcategoria_id,
        "amount": cantidad,
        "description": concepto,
    }
    try:
        response = requests.post(f"{API_URL}/transactions/", json=data)
        if response.status_code == 200:
            res = response.json()
            if "date" in res and "fecha" not in res:
                res["fecha"] = res["date"]
            if "amount" in res and "cantidad" not in res:
                res["cantidad"] = res["amount"]
            return res
        return None
    except Exception:
        return None


def save_presupuestos_bulk(presupuestos_list):
    payload = []
    for p in presupuestos_list:
        m = p.get("month") or p.get("mes")
        s = p.get("subcategory_id")
        a = p.get("amount") if p.get("amount") is not None else p.get("cantidad", 0.0)
        payload.append({"month": m, "subcategory_id": s, "amount": a})
    try:
        response = requests.post(f"{API_URL}/budgets/bulk", json=payload)
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None


def get_safety_status(mes=None):
    params = {}
    if mes:
        params["mes"] = mes
    try:
        response = requests.get(f"{API_URL}/advisor/safety-status", params=params)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def update_emergency_fund_config(target_months=None, current_balance=None, mes=None):
    params = {}
    if mes:
        params["mes"] = mes
    data = {}
    if target_months is not None:
        data["target_months"] = target_months
    if current_balance is not None:
        data["current_balance"] = current_balance
    try:
        response = requests.post(f"{API_URL}/advisor/emergency-fund/config", params=params, json=data)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None
