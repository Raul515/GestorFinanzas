"""
Pruebas unitarias para la Fase 2 de la Especificación 015:
Métodos de Cliente HTTP e Invalidación Selectiva de Caché en api_client.py.
"""

from unittest.mock import patch, MagicMock
import pytest
import requests
from frontend import api_client


# ==========================================
# 1. SUBCATEGORÍAS PERSONALES
# ==========================================

def test_create_subcategory_success():
    """Verifica que create_subcategory envíe POST, invalide caché e invoque clear_categories_cache y clear_annual_cache."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 10, "name": "Clases de Piano", "category_id": 2}

    with patch.object(api_client._session, "post", return_value=mock_resp) as mock_post, \
         patch.object(api_client, "clear_categories_cache") as mock_clear_cat, \
         patch.object(api_client, "clear_annual_cache") as mock_clear_ann:

        res = api_client.create_subcategory(category_id=2, name="  Clases de Piano  ")
        assert res == {"id": 10, "name": "Clases de Piano", "category_id": 2}
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["json"] == {"category_id": 2, "name": "Clases de Piano"}
        mock_clear_cat.assert_called_once()
        mock_clear_ann.assert_called_once()


def test_create_subcategory_empty_name():
    """Verifica que create_subcategory rechace nombres vacíos sin llamar al backend."""
    with patch.object(api_client._session, "post") as mock_post:
        res = api_client.create_subcategory(category_id=2, name="   ")
        assert res is None
        mock_post.assert_not_called()


def test_create_subcategory_error():
    """Verifica que si la API falla, create_subcategory retorne None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch.object(api_client._session, "post", return_value=mock_resp):
        res = api_client.create_subcategory(category_id=2, name="Test Error")
        assert res is None


def test_create_subcategory_network_exception():
    """Verifica manejo de RequestException al crear subcategoría."""
    with patch.object(api_client._session, "post", side_effect=requests.exceptions.ConnectionError("Offline")):
        res = api_client.create_subcategory(category_id=2, name="Test Red")
        assert res is None


def test_update_subcategory_success():
    """Verifica que update_subcategory envíe PUT, limpie caché y devuelva la entidad renombrada."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 5, "name": "Alquiler Principal", "category_id": 1}

    with patch.object(api_client._session, "put", return_value=mock_resp) as mock_put, \
         patch.object(api_client, "clear_categories_cache") as mock_clear_cat, \
         patch.object(api_client, "clear_annual_cache") as mock_clear_ann:

        res = api_client.update_subcategory(subcategory_id=5, name="Alquiler Principal")
        assert res == {"id": 5, "name": "Alquiler Principal", "category_id": 1}
        mock_put.assert_called_once()
        assert mock_put.call_args[1]["json"] == {"name": "Alquiler Principal"}
        mock_clear_cat.assert_called_once()
        mock_clear_ann.assert_called_once()


def test_update_subcategory_empty_name():
    """Verifica que update_subcategory no procese nombres vacíos."""
    with patch.object(api_client._session, "put") as mock_put:
        res = api_client.update_subcategory(subcategory_id=5, name="   ")
        assert res is None
        mock_put.assert_not_called()


def test_get_subcategory_usage_success():
    """Verifica consulta de auditoría de uso de una subcategoría personal."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "subcategory_id": 5,
        "transactions_count": 3,
        "budgets_count": 1,
        "can_delete": False,
    }

    with patch.object(api_client._session, "get", return_value=mock_resp) as mock_get:
        usage = api_client.get_subcategory_usage(5)
        assert usage is not None
        assert usage["can_delete"] is False
        assert usage["transactions_count"] == 3
        mock_get.assert_called_once()


def test_get_subcategory_usage_error():
    """Verifica que retorne None si el backend responde con error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Not found"

    with patch.object(api_client._session, "get", return_value=mock_resp):
        usage = api_client.get_subcategory_usage(999)
        assert usage is None


def test_delete_subcategory_success():
    """Verifica eliminación exitosa de subcategoría personal cuando no tiene dependencias."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"deleted": True, "subcategory_id": 5}

    with patch.object(api_client._session, "delete", return_value=mock_resp) as mock_del, \
         patch.object(api_client, "clear_categories_cache") as mock_clear_cat, \
         patch.object(api_client, "clear_annual_cache") as mock_clear_ann:

        ok, msg = api_client.delete_subcategory(5)
        assert ok is True
        assert "éxito" in msg.lower()
        mock_del.assert_called_once()
        mock_clear_cat.assert_called_once()
        mock_clear_ann.assert_called_once()


def test_delete_subcategory_conflict():
    """Verifica que ante HTTP 409 Conflict se retorne False con el mensaje explicativo."""
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.json.return_value = {"detail": "No se puede eliminar: tiene 2 transacciones vinculadas."}

    with patch.object(api_client._session, "delete", return_value=mock_resp):
        ok, msg = api_client.delete_subcategory(5)
        assert ok is False
        assert "tiene 2 transacciones" in msg


def test_delete_subcategory_network_error():
    """Verifica manejo de error de red en delete_subcategory."""
    with patch.object(api_client._session, "delete", side_effect=requests.exceptions.ConnectionError("Down")):
        ok, msg = api_client.delete_subcategory(5)
        assert ok is False
        assert "red" in msg.lower()


# ==========================================
# 2. SUBCATEGORÍAS DEL HOGAR (JOINT)
# ==========================================

def test_create_joint_subcategory_success():
    """Verifica creación de subcategoría del hogar e invalidación de clear_joint_cache."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": 8,
        "name": "Artículos de Limpieza",
        "joint_category_id": 1,
        "monthly_budget": 30.0,
    }

    with patch.object(api_client._session, "post", return_value=mock_resp) as mock_post, \
         patch.object(api_client, "clear_joint_cache") as mock_clear_joint:

        res = api_client.create_joint_subcategory("Artículos de Limpieza", joint_category_id=1, monthly_budget=30.0)
        assert res == {
            "id": 8,
            "name": "Artículos de Limpieza",
            "joint_category_id": 1,
            "monthly_budget": 30.0,
        }
        mock_post.assert_called_once()
        mock_clear_joint.assert_called_once()


def test_create_joint_subcategory_empty_name():
    """Verifica que rechace nombres vacíos para subcategorías del hogar."""
    with patch.object(api_client._session, "post") as mock_post:
        res = api_client.create_joint_subcategory("   ", joint_category_id=1)
        assert res is None
        mock_post.assert_not_called()


def test_update_joint_subcategory_success():
    """Verifica actualización de nombre y presupuesto en subcategoría del hogar."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 8,
        "name": "Limpieza y Droguería",
        "joint_category_id": 1,
        "monthly_budget": 40.0,
    }

    with patch.object(api_client._session, "put", return_value=mock_resp) as mock_put, \
         patch.object(api_client, "clear_joint_cache") as mock_clear_joint:

        res = api_client.update_joint_subcategory(8, name="Limpieza y Droguería", monthly_budget=40.0)
        assert res is not None
        assert res["monthly_budget"] == 40.0
        mock_put.assert_called_once()
        mock_clear_joint.assert_called_once()


def test_update_joint_subcategory_no_fields():
    """Verifica que update_joint_subcategory retorne None si no se especifica ningún campo."""
    res = api_client.update_joint_subcategory(8)
    assert res is None


def test_get_joint_subcategory_usage_success():
    """Verifica consulta de uso de subcategoría del hogar."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "subcategory_id": 8,
        "transactions_count": 0,
        "can_delete": True,
    }

    with patch.object(api_client._session, "get", return_value=mock_resp):
        usage = api_client.get_joint_subcategory_usage(8)
        assert usage == {"subcategory_id": 8, "transactions_count": 0, "can_delete": True}


def test_delete_joint_subcategory_success():
    """Verifica eliminación de subcategoría del hogar sin dependencias."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"deleted": True, "subcategory_id": 8}

    with patch.object(api_client._session, "delete", return_value=mock_resp), \
         patch.object(api_client, "clear_joint_cache") as mock_clear_joint:

        ok, msg = api_client.delete_joint_subcategory(8)
        assert ok is True
        assert "éxito" in msg.lower()
        mock_clear_joint.assert_called_once()


def test_delete_joint_subcategory_conflict():
    """Verifica bloqueo por dependencias (409 Conflict) en el hogar."""
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.json.return_value = {"detail": "No se puede eliminar: tiene 5 transacciones del hogar vinculadas."}

    with patch.object(api_client._session, "delete", return_value=mock_resp):
        ok, msg = api_client.delete_joint_subcategory(8)
        assert ok is False
        assert "5 transacciones" in msg



# ==========================================
# 3. PRESUPUESTO INDIVIDUAL (create_presupuesto)
# ==========================================

def test_create_presupuesto_success():
    """Verifica que create_presupuesto envíe POST a /budgets/ e invalide la caché del resumen anual."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 1,
        "month": "BASE",
        "subcategory_id": 10,
        "amount": 50.0,
    }

    with patch.object(api_client._session, "post", return_value=mock_resp) as mock_post,          patch.object(api_client, "clear_annual_cache") as mock_clear_ann:

        res = api_client.create_presupuesto("BASE", 10, 50.0)
        assert res is not None
        assert res["cantidad"] == 50.0
        assert res["mes"] == "BASE"
        mock_post.assert_called_once()
        mock_clear_ann.assert_called_once()


def test_create_presupuesto_error():
    """Verifica que retorne None si la API de presupuestos falla."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Server Error"

    with patch.object(api_client._session, "post", return_value=mock_resp):
        res = api_client.create_presupuesto("BASE", 10, 50.0)
        assert res is None
