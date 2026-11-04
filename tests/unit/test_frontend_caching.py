"""
Pruebas unitarias para la Fase 2 de la Especificación 014:
Estrategia de Caching en Frontend (@st.cache_data) e Invalidación Selectiva.
"""

from unittest.mock import patch, MagicMock
import pytest
from frontend import api_client


def test_cached_functions_have_cache_clear_attribute():
    """RF-6, RF-7, RF-8: Verifica que las funciones decoradas con @st.cache_data dispongan de .clear()."""
    cached_functions = [
        api_client.get_categorias,
        api_client.get_subcategorias,
        api_client.get_joint_categories,
        api_client.get_joint_subcategories,
        api_client.get_joint_sinking_funds,
        api_client.get_screener_universes,
        api_client.get_screener_universe,
        api_client.get_deepdive_analysis,
        api_client.get_macro_indicators,
        api_client.get_market_news,
        api_client.get_app_version,
    ]
    for fn in cached_functions:
        fn_name = getattr(fn, "__name__", str(fn))
        assert hasattr(fn, "clear"), f"La función {fn_name} no está decorada con @st.cache_data"


def test_clear_cache_helpers_run_without_errors():
    """RF-9: Verifica que las funciones auxiliares de invalidación selectiva se ejecuten sin excepciones."""
    # Debe ser posible invocar cada limpiador sin que lance ningún fallo
    api_client.clear_categories_cache()
    api_client.clear_market_cache()
    api_client.clear_joint_cache()
    api_client.clear_all_frontend_cache()


def test_get_categorias_caching_behavior():
    """RF-6: Verifica que get_categorias retorne datos cacheados evitando peticiones de red repetidas."""
    api_client.get_categorias.clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"id": 1, "name": "Ingresos", "type": "INGRESO", "subcategories": []}
    ]

    with patch.object(api_client._session, "get", return_value=mock_resp) as mock_get:
        # Primera llamada: hace la petición HTTP
        res1 = api_client.get_categorias()
        assert len(res1) == 1
        assert res1[0]["name"] == "Ingresos"
        assert mock_get.call_count == 1

        # Segunda llamada con idénticos parámetros: se sirve desde caché
        res2 = api_client.get_categorias()
        assert len(res2) == 1
        assert mock_get.call_count == 1  # No debe haber hecho otra llamada HTTP

        # Invalidar la caché
        api_client.clear_categories_cache()

        # Tercera llamada: vuelve a consultar al backend
        res3 = api_client.get_categorias()
        assert len(res3) == 1
        assert mock_get.call_count == 2


def test_get_screener_universe_caching_behavior():
    """RF-7: Verifica que el Screener cachee el universo de 30 minutos."""
    api_client.get_screener_universe.clear()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "universe_id": "ibex35",
        "items": [{"ticker": "SAN.MC", "price": 4.5}],
        "total_count": 1,
    }

    with patch.object(api_client._session, "get", return_value=mock_resp) as mock_get:
        # Llamada 1
        d1 = api_client.get_screener_universe("ibex35")
        assert d1 is not None
        assert mock_get.call_count == 1

        # Llamada 2 con mismos argumentos: desde caché
        d2 = api_client.get_screener_universe("ibex35")
        assert d2 is not None
        assert mock_get.call_count == 1

        # Al refrescar deliberadamente el screener, se limpia la caché
        mock_post = MagicMock()
        mock_post.status_code = 200
        mock_post.json.return_value = {"status": "refreshed"}
        with patch.object(api_client._session, "post", return_value=mock_post):
            api_client.refresh_screener_universe("ibex35")

        # Siguiente llamada: vuelve a consultar a la red
        d3 = api_client.get_screener_universe("ibex35")
        assert d3 is not None
        assert mock_get.call_count == 2


def test_joint_sinking_funds_mutation_invalidates_cache():
    """RF-8, RF-9: Verifica que las operaciones de mutación en huchas invaliden su caché."""
    api_client.get_joint_sinking_funds.clear()

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = [{"id": 1, "name": "Coche", "current_balance": 500.0}]

    with patch.object(api_client._session, "get", return_value=mock_get_resp) as mock_get:
        # Consulta inicial
        f1 = api_client.get_joint_sinking_funds()
        assert len(f1) == 1
        assert mock_get.call_count == 1

        # Consulta repetida inmediata: caché
        f2 = api_client.get_joint_sinking_funds()
        assert len(f2) == 1
        assert mock_get.call_count == 1

        # Crear una hucha: dispara invalidación de get_joint_sinking_funds
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 201
        mock_post_resp.json.return_value = {"id": 2, "name": "Vacaciones"}
        with patch.object(api_client._session, "post", return_value=mock_post_resp):
            api_client.create_joint_sinking_fund({"name": "Vacaciones", "target_amount": 1000.0})

        # Siguiente consulta: debe ir de nuevo a la red
        f3 = api_client.get_joint_sinking_funds()
        assert len(f3) == 1
        assert mock_get.call_count == 2

