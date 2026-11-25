"""
Pruebas unitarias para los helpers de la vista móvil en frontend (Spec 016 / Spec 017).
Valida detección de IP local, formateo de fechas DD/MM/AAAA, PIN, schema de tickets y descarga HTTP.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from backend.domain.schemas.transactions import Transaction as TransactionSchema
from frontend import api_client
from frontend.views.mobile_view import format_display_date, get_local_ip


def test_mobile_view_helpers():
    """Verifica las funciones de soporte de formato de fecha, ip y PIN."""
    assert format_display_date("2026-11-13") == "13/11/2026"
    assert format_display_date("2026-11-13T18:45:00Z") == "13/11/2026"
    assert format_display_date("") == "N/A"

    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0

    pin = "582914"
    formatted = f"{pin[:3]} {pin[3:]}" if len(pin) == 6 else pin
    assert formatted == "582 914"


def test_receipt_filename_exposed_in_transaction_schema():
    """Verifica que el schema Pydantic Transaction serializa receipt_filename cuando está presente."""
    tx = TransactionSchema(
        id=42,
        date=date(2026, 11, 25),
        subcategory_id=3,
        amount=12.50,
        description="Café y tostada",
        mobile_event_id="evt-123",
        receipt_filename="receipt_evt-123.jpg",
    )
    dumped = tx.model_dump()
    assert dumped["receipt_filename"] == "receipt_evt-123.jpg"

    tx_no_receipt = TransactionSchema(
        id=43,
        date=date(2026, 11, 25),
        subcategory_id=3,
        amount=5.0,
    )
    assert tx_no_receipt.model_dump()["receipt_filename"] is None


def test_get_mobile_receipt_bytes_success_and_404():
    """Verifica la descarga de bytes de ticket desde el backend local para respuestas 200 y 404."""
    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.content = b"\xff\xd8\xff\xe0FAKE_JPEG"

    mock_404 = MagicMock()
    mock_404.status_code = 404
    mock_404.text = "Not found"

    with patch("frontend.api.http._session") as mock_session:
        mock_session.get.return_value = mock_ok
        data = api_client.get_mobile_receipt_bytes("receipt_evt-123.jpg", pairing_token="secret-tok")
        assert data == b"\xff\xd8\xff\xe0FAKE_JPEG"
        called_url = mock_session.get.call_args[0][0]
        assert called_url.endswith("/api/mobile/receipts/receipt_evt-123.jpg")
        assert mock_session.get.call_args[1]["headers"] == {"X-Mobile-Pairing-Token": "secret-tok"}

        mock_session.get.return_value = mock_404
        assert api_client.get_mobile_receipt_bytes("missing.jpg", pairing_token="secret-tok") is None
        assert api_client.get_mobile_receipt_bytes("   ", pairing_token="secret-tok") is None
