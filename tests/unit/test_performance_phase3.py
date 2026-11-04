"""
Pruebas unitarias para la Fase 3 de la Especificación 014:
Optimización del Ciclo de Vida Streamlit, Lazy Loading y Exportación Eager.
"""

from unittest.mock import MagicMock, patch
import ast
import os
import pytest
from frontend import api_client
from backend.services.joint_accounting_service import generate_household_excel_export


def test_annual_summary_caching_and_invalidation():
    """RF-10: Valida que get_annual_summary_data almacena en caché los 12 meses y se invalida."""
    api_client.get_annual_summary_data.clear()

    mock_presupuestos = [{"id": 1, "month": "2026-01", "amount": 100.0, "subcategory_id": 1}]
    mock_transacciones = [{"id": 1, "date": "2026-01-15", "amount": 50.0, "subcategory_id": 1}]

    with patch.object(api_client, "get_presupuestos", return_value=mock_presupuestos) as mock_p, \
         patch.object(api_client, "get_transacciones", return_value=mock_transacciones) as mock_t:
        
        # Primera llamada: consulta los 12 meses (12 llamadas a presupuestos y 12 a transacciones)
        data1 = api_client.get_annual_summary_data(2026)
        assert len(data1) == 12
        assert data1[1]["presupuestos"] == mock_presupuestos
        assert mock_p.call_count == 12
        assert mock_t.call_count == 12

        # Segunda llamada con idéntico año: servido desde caché RAM (0 llamadas de red)
        data2 = api_client.get_annual_summary_data(2026)
        assert len(data2) == 12
        assert mock_p.call_count == 12
        assert mock_t.call_count == 12

        # Invalidación manual mediante helper
        api_client.clear_annual_cache()

        # Tercera llamada: vuelve a consultar
        data3 = api_client.get_annual_summary_data(2026)
        assert len(data3) == 12
        assert mock_p.call_count == 24
        assert mock_t.call_count == 24


def test_transaction_creation_invalidates_annual_cache():
    """RF-10: Valida que crear una transacción invalida la caché del resumen anual."""
    api_client.get_annual_summary_data.clear()

    with patch.object(api_client, "get_presupuestos", return_value=[]) as mock_p, \
         patch.object(api_client, "get_transacciones", return_value=[]) as mock_t:
        
        api_client.get_annual_summary_data(2026)
        assert mock_p.call_count == 12

        # Simular creación de transacción exitosa
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 99, "amount": 25.0}

        with patch.object(api_client._session, "post", return_value=mock_resp):
            api_client.create_transaccion("2026-02-10", 1, 25.0, "Supermercado")

        # Siguiente llamada a get_annual_summary_data: debe regenerar la caché
        api_client.get_annual_summary_data(2026)
        assert mock_p.call_count == 24


def test_export_joint_excel_caching_and_invalidation():
    """RF-12: Valida que export_joint_excel() se almacena en caché e invalida ante mutaciones."""
    api_client.export_joint_excel.clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake-excel-content"

    with patch.object(api_client._session, "get", return_value=mock_resp) as mock_get:
        # Llamada 1
        res1 = api_client.export_joint_excel()
        assert res1 == b"fake-excel-content"
        assert mock_get.call_count == 1

        # Llamada 2 inmediata: desde caché RAM
        res2 = api_client.export_joint_excel()
        assert res2 == b"fake-excel-content"
        assert mock_get.call_count == 1

        # Invalidar caché conjunta
        api_client.clear_joint_cache()

        # Llamada 3: vuelve a consultar al backend
        res3 = api_client.export_joint_excel()
        assert res3 == b"fake-excel-content"
        assert mock_get.call_count == 2


def test_app_py_deepdive_lazy_loading_code_structure():
    """RF-11: Verifica que en app.py el análisis de Deep Dive requiere click explícito."""
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    with open(app_path, "r", encoding="utf-8") as f:
        code = f.read()

    # No debe existir la auto-ejecución incondicional por ausencia en session_state
    assert 'f"deepdive_data_{active_ticker}" not in st.session_state:' not in code
    # Debe requerir analizar_clicked explícito
    assert 'elif analizar_clicked:' in code


def test_joint_accounting_service_uses_joinedload():
    """RF-12: Verifica que generate_household_excel_export incorpora joinedload para resolver N+1 queries."""
    service_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/backend/services/joint_accounting_service.py"))
    with open(service_path, "r", encoding="utf-8") as f:
        code = f.read()

    assert "joinedload(JointTransaction.joint_subcategory)" in code
    assert "joinedload(JointTransaction.joint_sinking_fund)" in code

