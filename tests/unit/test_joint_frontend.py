"""
Pruebas Unitarias para el Módulo Frontend de la Cuenta Conjunta (Spec 010).
Valida los métodos de api_client y la resiliencia ante errores de red.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from frontend import api_client


# =====================================================================
# 1. PRUEBAS DE MÉTODOS DE API_CLIENT PARA LA CUENTA CONJUNTA
# =====================================================================

def test_api_client_get_joint_status_success():
    """Valida la consulta exitosa del estado de configuración."""
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"is_configured": True}
        mock_get.return_value = mock_resp

        status = api_client.get_joint_status()
        assert status == {"is_configured": True}
        mock_get.assert_called_once()


def test_api_client_get_joint_status_failure():
    """Valida la resiliencia cuando el backend no está disponible o falla."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        status = api_client.get_joint_status()
        assert status == {"is_configured": False}


def test_api_client_setup_joint_account():
    """Valida el envío del formulario de onboarding inicial."""
    payload = {
        "account_name": "Hogar Prueba",
        "member_a_name": "Raúl",
        "member_b_name": "Ana",
        "split_mode": "EQUAL",
        "cohabitation_stage": "DATING_COHABITATION",
        "member_a_estimated_income": 2000.0,
        "member_b_estimated_income": 2000.0,
    }
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {**payload, "id": 1, "is_active": True}
        mock_post.return_value = mock_resp

        res = api_client.setup_joint_account(payload)
        assert res is not None
        assert res["account_name"] == "Hogar Prueba"
        mock_post.assert_called_once()


def test_api_client_sinking_funds_crud():
    """Valida creación, edición y eliminación de huchas de amortización."""
    # Create
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 1, "name": "Seguro Coche", "target_amount": 600.0}
        mock_post.return_value = mock_resp

        res_create = api_client.create_joint_sinking_fund({"name": "Seguro Coche", "target_amount": 600.0})
        assert res_create is not None
        assert res_create["id"] == 1

    # Update
    with patch("requests.put") as mock_put:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "current_balance": 150.0}
        mock_put.return_value = mock_resp

        res_update = api_client.update_joint_sinking_fund(1, {"current_balance": 150.0})
        assert res_update is not None
        assert res_update["current_balance"] == 150.0

    # Delete
    with patch("requests.delete") as mock_del:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_del.return_value = mock_resp

        ok = api_client.delete_joint_sinking_fund(1, reallocate_to_fund_id=2)
        assert ok is True


def test_api_client_transactions_and_contributions():
    """Valida gestión de transacciones y aportaciones asistidas."""
    # Create Transaction
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 10, "amount": 45.0, "description": "Luz"}
        mock_post.return_value = mock_resp

        tx = api_client.create_joint_transaction({
            "description": "Luz",
            "amount": 45.0,
            "date": "2026-11-01",
            "created_by_profile": "MEMBER_A",
        })
        assert tx is not None
        assert tx["id"] == 10

    # Delete Transaction
    with patch("requests.delete") as mock_del:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_del.return_value = mock_resp

        ok = api_client.delete_joint_transaction(10)
        assert ok is True

    # Assisted Contribution
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": 1, "amount": 600.0, "month": "2026-11"}
        mock_post.return_value = mock_resp

        res_asistida = api_client.asentar_aportacion_asistida({
            "month": "2026-11",
            "amount": 600.0,
            "contributor_profile": "MEMBER_A",
        })
        assert res_asistida is not None
        assert res_asistida["month"] == "2026-11"


def test_api_client_annual_summary_and_health():
    """Valida la consulta de Resumen Anual y Salud Financiera del Hogar."""
    # Annual Summary
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "year": 2026,
            "total_needs_spent": 12000.0,
            "total_sinking_funds_saved": 3500.0,
            "effort_rate_pct": 35.0,
            "health_status": "SUSTAINABLE",
            "monthly_metrics": [],
        }
        mock_get.return_value = mock_resp

        summary = api_client.get_joint_annual_summary(2026)
        assert summary is not None
        assert summary["total_needs_spent"] == 12000.0
        assert summary["health_status"] == "SUSTAINABLE"

    # Health diagnostic
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "joint_needs_budget": 1200.0,
            "combined_reference_income": 4000.0,
            "effort_rate_pct": 30.0,
            "status": "SUSTAINABLE",
            "message": "Saludable",
        }
        mock_get.return_value = mock_resp

        health = api_client.get_joint_health()
        assert health is not None
        assert health["effort_rate_pct"] == 30.0


def test_api_client_sync_endpoints():
    """Valida los endpoints de sincronización de Syncthing."""
    # Status
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "is_synchronized": True,
            "outbox_pending_count": 0,
            "inbox_pending_count": 0,
        }
        mock_get.return_value = mock_resp

        sync_st = api_client.get_sync_status()
        assert sync_st["is_synchronized"] is True

    # Trigger process inbox
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "processed_count": 2,
            "ignored_count": 0,
        }
        mock_post.return_value = mock_resp

        inbox_res = api_client.trigger_process_inbox()
        assert inbox_res["processed_count"] == 2


# =====================================================================
# 2. PRUEBAS DE ENRUTAMIENTO DE VISTA JOINT_VIEW
# =====================================================================

def test_render_joint_view_routes_to_wizard_when_unconfigured():
    """Verifica que si la cuenta no está configurada, render_joint_view invoca el onboarding wizard."""
    from frontend.views import joint_view

    with patch.object(joint_view.api_client, "get_joint_status", return_value={"is_configured": False}), \
         patch.object(joint_view, "_render_zero_state_wizard") as mock_wizard:
        joint_view.render_joint_view(selected_year=2026)
        mock_wizard.assert_called_once()


def test_render_joint_view_routes_to_dashboard_when_configured():
    """Verifica que si la cuenta está configurada, render_joint_view invoca la vista completa."""
    from frontend.views import joint_view

    with patch.object(joint_view.api_client, "get_joint_status", return_value={"is_configured": True}), \
         patch.object(joint_view.api_client, "get_joint_account", return_value={"id": 1, "account_name": "Hogar"}), \
         patch.object(joint_view, "_render_configured_joint_view") as mock_dashboard:
        joint_view.render_joint_view(selected_year=2026)
        mock_dashboard.assert_called_once()
