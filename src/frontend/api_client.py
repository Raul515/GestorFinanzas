import requests
import os

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")

def get_categorias():
    try:
        response = requests.get(f"{API_URL}/categorias/")
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def get_subcategorias(categoria_id=None):
    params = {}
    if categoria_id:
        params["categoria_id"] = categoria_id
    try:
        response = requests.get(f"{API_URL}/categorias/subcategorias/", params=params)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def get_presupuestos(mes):
    try:
        response = requests.get(f"{API_URL}/presupuestos/{mes}")
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def get_transacciones(mes=None):
    params = {}
    if mes:
        params["mes"] = mes
    try:
        response = requests.get(f"{API_URL}/transacciones/", params=params)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []

def create_transaccion(fecha, subcategoria_id, cantidad, concepto):
    data = {
        "fecha": fecha.isoformat(),
        "subcategoria_id": subcategoria_id,
        "cantidad": cantidad,
        "concepto": concepto
    }
    try:
        response = requests.post(f"{API_URL}/transacciones/", json=data)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def save_presupuestos_bulk(presupuestos_list):
    try:
        response = requests.post(f"{API_URL}/presupuestos/bulk", json=presupuestos_list)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def get_safety_status(mes=None):
    params = {}
    if mes:
        params["mes"] = mes
    try:
        response = requests.get(f"{API_URL}/advisor/safety-status", params=params)
        if response.status_code == 200:
            return response.json()
    except:
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
    except:
        pass
    return None
