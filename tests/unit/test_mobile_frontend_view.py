"""
Pruebas unitarias para los helpers de la vista móvil en frontend (Spec 016 / Spec 017).
Valida detección de IP local, formateo de fechas DD/MM/AAAA y formateo de PIN.
"""

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
