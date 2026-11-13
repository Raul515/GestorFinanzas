"""
Pruebas unitarias para la vista frontend y el generador QR de la micro-app móvil (Spec 016).
Valida:
- Generación de SVG puro y matriz de bits con QrCode.
- Detección de IP local y formateo de fechas DD/MM/AAAA.
"""

from frontend.qrcodegen import QrCode
from frontend.views.mobile_view import format_display_date, generate_qr_svg_base64, get_local_ip


def test_qrcodegen_svg_generation_and_validity():
    """Verifica que el generador QR en Python puro genere un SVG válido con dimensiones correctas."""
    url = "http://192.168.1.50:8000/mobile/"
    qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
    assert qr.size > 20
    assert qr.version >= 1

    svg_str = qr.to_svg_str(border=4)
    assert svg_str.startswith("<svg")
    assert svg_str.endswith("</svg>")
    assert "xmlns=\"http://www.w3.org/2000/svg\"" in svg_str
    assert "rect" in svg_str


def test_mobile_view_helpers():
    """Verifica las funciones de soporte de formato de fecha, ip y base64."""
    # Formato de fechas a DD/MM/AAAA (Regla 12)
    assert format_display_date("2026-11-13") == "13/11/2026"
    assert format_display_date("2026-11-13T18:45:00Z") == "13/11/2026"
    assert format_display_date("") == "N/A"

    # Generación de data uri base64
    data_uri = generate_qr_svg_base64("http://localhost:8000/mobile/")
    assert data_uri.startswith("data:image/svg+xml;base64,")
    assert len(data_uri) > 100

    # Detección de IP local
    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip) > 0
