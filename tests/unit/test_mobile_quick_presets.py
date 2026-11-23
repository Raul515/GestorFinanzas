"""
Pruebas Unitarias para Atajos Rápidos de Importe y Presets Frecuentes (Spec 016 - Fase 14).
Valida contratos de datos de presets, flujo de sincronización de guardado directo 1-Tap,
y la salvaguarda predictiva para categorías de Deseos (30%).
"""

from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.domain.models.categories import Category, Subcategory
from backend.domain.models.transactions import Transaction
from backend.domain.schemas.mobile import (
    MobileSyncRequest,
    MobileTransactionPayload,
)
from backend.services.mobile_sync_service import MobileSyncService


# Presets por defecto definidos en la especificación RF-18
DEFAULT_PRESETS_DATA = [
    {
        "id": "preset-cafe",
        "name": "Café",
        "emoji": "☕",
        "amount": 1.50,
        "subcategory_name": "Café y Desayunos",
        "concept": "Café",
    },
    {
        "id": "preset-cena",
        "name": "Cena",
        "emoji": "🍽️",
        "amount": 20.00,
        "subcategory_name": "Restaurante",
        "concept": "Cena",
    },
    {
        "id": "preset-cine",
        "name": "Cine",
        "emoji": "🎬",
        "amount": 5.50,
        "subcategory_name": "Ocio y Cultura",
        "concept": "Cine",
    },
]


def calculate_wants_safeguard_status(wants_budget: float, current_wants_spent: float, new_amount: float) -> dict:
    """Fórmula client-side del semáforo predictivo para salvaguarda de Deseos (RF-18)."""
    projected = current_wants_spent + new_amount
    ratio = projected / wants_budget if wants_budget > 0 else 1.0
    remaining = wants_budget - projected
    if ratio >= 1.0:
        return {
            "level": "OVER_LIMIT",
            "color": "rose",
            "projected_spent": projected,
            "remaining": remaining,
            "can_direct_save": False,
        }
    elif ratio >= 0.80:
        return {
            "level": "WARNING",
            "color": "amber",
            "projected_spent": projected,
            "remaining": remaining,
            "can_direct_save": True,
        }
    else:
        return {
            "level": "OK",
            "color": "emerald",
            "projected_spent": projected,
            "remaining": remaining,
            "can_direct_save": True,
        }


@pytest.fixture
def populated_db(db_session: Session) -> Session:
    """Prepara categorías y subcategorías base para las pruebas de presets."""
    cat_nec = Category(name="Necesidades Básicas (50%)", type="expense")
    cat_des = Category(name="Deseos (30%)", type="expense")
    cat_aho = Category(name="Ahorro e Inversión (20%)", type="expense")
    cat_ing = Category(name="Ingresos Netos", type="income")
    db_session.add_all([cat_nec, cat_des, cat_aho, cat_ing])
    db_session.commit()

    sub_cafe = Subcategory(name="Café y Desayunos", category_id=cat_des.id)
    sub_rest = Subcategory(name="Restaurante", category_id=cat_des.id)
    sub_ocio = Subcategory(name="Ocio y Cultura", category_id=cat_des.id)
    sub_super = Subcategory(name="Supermercado", category_id=cat_nec.id)

    db_session.add_all([sub_cafe, sub_rest, sub_ocio, sub_super])
    db_session.commit()
    return db_session


def test_default_quick_presets_structure_and_matching(populated_db: Session):
    """Verifica que los presets por defecto tienen la estructura requerida y corresponden a subcategorías válidas."""
    service = MobileSyncService()
    catalog = service.get_mobile_catalog(populated_db)
    available_subcat_names = {s.name.lower() for s in catalog.personal_subcategories}

    for preset in DEFAULT_PRESETS_DATA:
        assert "id" in preset and preset["id"].startswith("preset-")
        assert "name" in preset and len(preset["name"]) > 0
        assert "amount" in preset and preset["amount"] > 0
        assert "concept" in preset and len(preset["concept"]) > 0
        assert preset["subcategory_name"].lower() in available_subcat_names


def test_preset_direct_save_1tap_sync_flow(populated_db: Session):
    """Verifica la persistencia y sincronización tras un guardado directo 1-Tap de un preset."""
    service = MobileSyncService()
    sub_cafe = populated_db.query(Subcategory).filter(Subcategory.name == "Café y Desayunos").first()
    assert sub_cafe is not None

    # Simular guardado directo 1-Tap desde el preset 'Café'
    event_id = "mob-1tap-20261123-01"
    req = MobileSyncRequest(
        device_id="mobile-tester",
        transactions=[
            MobileTransactionPayload(
                event_id=event_id,
                amount=1.50,
                description="Café matutino",
                date=date(2026, 11, 23),
                subcategory_id=sub_cafe.id,
                subcategory_name="Café y Desayunos",
            )
        ],
    )

    res = service.process_mobile_sync(populated_db, req)
    assert res.processed_count == 1
    assert res.ignored_duplicates_count == 0

    # Verificar registro en base de datos
    tx = populated_db.query(Transaction).filter(Transaction.description == "Café matutino").first()
    assert tx is not None
    assert tx.amount == 1.50
    assert tx.subcategory_id == sub_cafe.id
    assert tx.date == date(2026, 11, 23)


def test_wants_preset_safeguard_prediction_blocks_over_limit(populated_db: Session):
    """
    Verifica la salvaguarda de Deseos:
    Si un preset de Deseos empujaría el gasto más allá del 30% asignado, el estado predictivo
    pasa a OVER_LIMIT, lo que permite al frontend bloquear el guardado directo automático
    y abrir el formulario para confirmación consciente.
    """
    # Presupuesto: 1000 € ingresos -> Deseos = 300 € (30%)
    # Gasto previo en deseos: 290 € (remanente = 10 €)
    # Un preset de 20 € (Cena) provocaría gasto total de 310 € (> 300 €)
    wants_budget = 300.0
    current_wants_spent = 290.0
    preset_amount = 20.0  # Preset Cena

    status = calculate_wants_safeguard_status(
        wants_budget=wants_budget,
        current_wants_spent=current_wants_spent,
        new_amount=preset_amount,
    )

    assert status["level"] == "OVER_LIMIT"
    assert status["color"] == "rose"
    assert status["projected_spent"] == 310.0
    assert status["remaining"] == -10.0
    assert status["can_direct_save"] is False


def test_wants_preset_safeguard_prediction_allows_safe_preset(populated_db: Session):
    """
    Verifica que si el preset está cómodamente dentro del margen de Deseos,
    el estado predictivo es OK (verde) y se autoriza el guardado directo 1-Tap.
    """
    wants_budget = 300.0
    current_wants_spent = 100.0
    preset_amount = 1.50  # Preset Café

    status = calculate_wants_safeguard_status(
        wants_budget=wants_budget,
        current_wants_spent=current_wants_spent,
        new_amount=preset_amount,
    )

    assert status["level"] == "OK"
    assert status["color"] == "emerald"
    assert status["projected_spent"] == 101.50
    assert status["remaining"] == 198.50
    assert status["can_direct_save"] is True


def test_custom_preset_creation_and_sync_fallback_by_name(populated_db: Session):
    """Verifica que un preset personalizado creado por el usuario con resolución por nombre sincroniza sin fallo."""
    service = MobileSyncService()

    # Usuario crea un preset para 'Supermercado' con subcategory_id omitido o negativo
    req = MobileSyncRequest(
        device_id="mobile-tester",
        transactions=[
            MobileTransactionPayload(
                event_id="mob-custom-preset-01",
                amount=12.80,
                description="Compra merienda",
                date=date(2026, 11, 23),
                subcategory_id=-1,
                subcategory_name="Supermercado",
            )
        ],
    )

    res = service.process_mobile_sync(populated_db, req)
    assert res.processed_count == 1

    tx = populated_db.query(Transaction).filter(Transaction.description == "Compra merienda").first()
    assert tx is not None
    assert tx.amount == 12.80
    assert tx.subcategory.name == "Supermercado"


def test_mobile_quick_presets_and_hybrid_1tap_pwa_bundle(client: TestClient):
    """Verifica que el bundle PWA estático en /mobile/ incluya los componentes y lógica de Presets 1-Tap (Fase 14)."""
    resp = client.get("/mobile/")
    assert resp.status_code == 200
    html = resp.text

    # 1. Clave de almacenamiento local y presets por defecto
    assert "gestor_mobile_quick_presets" in html
    assert "preset-cafe" in html
    assert "Café" in html
    assert "1.5" in html or "1.50" in html
    assert "Cena" in html
    assert "20" in html or "20.00" in html
    assert "Cine" in html
    assert "5.5" in html or "5.50" in html

    # 2. Funciones de renderizado y lógica híbrida (tap / long-press / undo)
    assert "renderQuickPresets" in html
    assert "renderManagePresetsModal" in html
    assert "handleDirectSavePreset" in html
    assert "handleSelectPreset" in html
    assert "undoDirectSave" in html

    # 3. Micro-guía visual accesible para el usuario
    assert "Toca para rellenar" in html
    assert "Mantén pulsado para" in html

