"""
Pruebas unitarias para el motor de sincronización asíncrona desacoplada (Spec 010 - Fase 3).
Verifica emisión atómica a outbox, ingesta idempotente de inbox, resolución determinista LWW,
gestión de tombstones y aislamiento estricto de datos privados.
"""

from datetime import date, datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import uuid
import pytest
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.models.joint import (
    JointAccount,
    JointAppliedSyncEvent,
    JointCategory,
    JointMonthlyContribution,
    JointSinkingFund,
    JointSubcategory,
    JointTransaction,
)
from backend.domain.schemas.joint import (
    CohabitationStage,
    ContributionStrategy,
    JointAccountSetupRequest,
    ProfileIdentifier,
    SplitMode,
    SyncAction,
    SyncEntityType,
    SyncEventPayload,
)
from backend.services.joint_sync_service import JointSyncService


@pytest.fixture
def temp_sync_dir():
    """Proporciona un directorio temporal aislado para buzones outbox, inbox y processed."""
    temp_dir = tempfile.mkdtemp(prefix="test_sync_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def setup_household_db(db_session: Session):
    """Inicializa la cuenta conjunta y subcategorías base para las pruebas de sincronización."""
    account = JointAccount(id=1, household_name="Hogar Sincronizado", local_profile="MEMBER_A", remote_profile="MEMBER_B")
    db_session.add(account)
    db_session.flush()

    cat = JointCategory(joint_account_id=1, name="Necesidades Básicas", type="JOINT_NEEDS")
    db_session.add(cat)
    db_session.flush()

    subcat = JointSubcategory(joint_category_id=cat.id, name="Supermercado", monthly_budget=400.0)
    db_session.add(subcat)

    fund = JointSinkingFund(
        joint_account_id=1,
        name="Viajes",
        target_amount=2000.0,
        current_balance=800.0,
        status="ACTIVE",
    )
    db_session.add(fund)
    db_session.commit()
    return {"account": account, "category": cat, "subcategory": subcat, "fund": fund}


def test_emit_event_atomic(temp_sync_dir: str):
    """Verifica que emit_event deposite de forma atómica ficheros JSON válidos en outbox sin dejar .tmp."""
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_A")

    payload = {"uuid": str(uuid.uuid4()), "amount": 45.0, "description": "Luz"}
    event = service.emit_event(
        entity_type=SyncEntityType.TRANSACTION,
        action=SyncAction.UPSERT,
        payload=payload,
    )

    outbox_files = list((Path(temp_sync_dir) / "outbox").iterdir())
    assert len(outbox_files) == 1
    assert outbox_files[0].name == f"evt_{event.event_id}.json"
    assert not outbox_files[0].name.endswith(".tmp")

    with open(outbox_files[0], "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["event_id"] == event.event_id
    assert data["entity_type"] == "TRANSACTION"
    assert data["action"] == "UPSERT"
    assert data["origin_device_id"] == "PC_USUARIO_A"


def test_idempotency_duplicate_event(temp_sync_dir: str, db_session: Session, setup_household_db: dict):
    """Verifica que procesar el mismo evento dos veces consecutivas no duplique transacciones ni saldos."""
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_A")

    tx_uuid = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    subcat = setup_household_db["subcategory"]

    event_data = {
        "event_id": event_id,
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "MAC_USUARIO_B",
        "timestamp_utc": "2026-11-01T15:00:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-01",
            "amount": 75.0,
            "description": "Compra conjunta en Mercadona",
            "joint_subcategory_id": subcat.id,
            "created_by_profile": "MEMBER_B",
        },
    }

    # 1. Depositar evento en inbox y procesar por primera vez
    inbox_file = Path(temp_sync_dir) / "inbox" / f"evt_{event_id}.json"
    with open(inbox_file, "w", encoding="utf-8") as f:
        json.dump(event_data, f)

    res1 = service.process_inbox(db_session)
    assert res1["processed_count"] == 1
    assert res1["skipped_count"] == 0
    assert db_session.query(JointTransaction).filter_by(uuid=tx_uuid).count() == 1

    # 2. Simular que Syncthing deposita el mismo evento por segunda vez (retransmisión de red)
    inbox_file_dup = Path(temp_sync_dir) / "inbox" / f"evt_{event_id}.json"
    with open(inbox_file_dup, "w", encoding="utf-8") as f:
        json.dump(event_data, f)

    res2 = service.process_inbox(db_session)
    assert res2["processed_count"] == 0
    assert res2["skipped_count"] == 1  # Detectado por idempotencia en BD y descartado silenciosamente
    # No se ha duplicado en la base de datos
    assert db_session.query(JointTransaction).filter_by(uuid=tx_uuid).count() == 1


def test_lww_conflict_resolution(temp_sync_dir: str, db_session: Session, setup_household_db: dict):
    """
    Verifica la resolución determinista de conflictos Last-Write-Wins (LWW):
    Si llegan dos ediciones concurrentes para el mismo UUID, prevalece la de mayor timestamp_utc.
    """
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_A")
    subcat = setup_household_db["subcategory"]
    tx_uuid = str(uuid.uuid4())

    # Evento A (Más reciente): 12:10 UTC, importe 95.0 €
    evt_newer = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "MAC_USUARIO_B",
        "timestamp_utc": "2026-11-01T12:10:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-01",
            "amount": 95.0,
            "description": "Edición posterior (correcta)",
            "joint_subcategory_id": subcat.id,
        },
    }

    # Evento B (Más antiguo): 12:05 UTC, importe 50.0 €
    evt_older = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "MAC_USUARIO_B",
        "timestamp_utc": "2026-11-01T12:05:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-01",
            "amount": 50.0,
            "description": "Edición anterior obsoleta",
            "joint_subcategory_id": subcat.id,
        },
    }

    # 1. Aplicar primero el evento más reciente
    with open(Path(temp_sync_dir) / "inbox" / "evt_newer.json", "w", encoding="utf-8") as f:
        json.dump(evt_newer, f)
    service.process_inbox(db_session)

    tx = db_session.query(JointTransaction).filter_by(uuid=tx_uuid).first()
    assert tx is not None
    assert tx.amount == 95.0

    # 2. Llega posteriormente el evento más antiguo por retraso de conexión
    with open(Path(temp_sync_dir) / "inbox" / "evt_older.json", "w", encoding="utf-8") as f:
        json.dump(evt_older, f)
    service.process_inbox(db_session)

    # La regla LWW descarta el cambio antiguo y mantiene el de 95.0 €
    db_session.refresh(tx)
    assert tx.amount == 95.0
    assert tx.description == "Edición posterior (correcta)"


def test_tombstone_delete_and_revert_sinking_fund(temp_sync_dir: str, db_session: Session, setup_household_db: dict):
    """
    Verifica que un evento DELETE (tombstone) elimine el apunte y devuelva el saldo a la hucha de amortización.
    """
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_A")
    fund = setup_household_db["fund"]  # Saldo inicial = 800.0 €
    tx_uuid = str(uuid.uuid4())

    # 1. Crear transacción con cargo a la hucha (gasto de 200 €)
    evt_upsert = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "MAC_USUARIO_B",
        "timestamp_utc": "2026-11-01T14:00:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-01",
            "amount": 200.0,
            "description": "Billetes de tren",
            "joint_sinking_fund_id": fund.id,
        },
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_create.json", "w", encoding="utf-8") as f:
        json.dump(evt_upsert, f)
    service.process_inbox(db_session)

    db_session.refresh(fund)
    assert fund.current_balance == 600.0  # 800 - 200

    # 2. Llega un tombstone de borrado
    evt_delete = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "DELETE",
        "origin_device_id": "MAC_USUARIO_B",
        "timestamp_utc": "2026-11-01T14:15:00Z",
        "payload": {"uuid": tx_uuid},
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_delete.json", "w", encoding="utf-8") as f:
        json.dump(evt_delete, f)
    service.process_inbox(db_session)

    # Transacción eliminada y saldo de la hucha restaurado a 800.0 €
    assert db_session.query(JointTransaction).filter_by(uuid=tx_uuid).first() is None
    db_session.refresh(fund)
    assert fund.current_balance == 800.0


def test_sync_isolation_no_personal_data(temp_sync_dir: str):
    """
    Certifica el RNF-2 y Principio 10: En la sincronización solo viajan tipos de entidad del espacio conjunto.
    Queda validado por contrato tipado de Pydantic.
    """
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_A")

    # Emisión legítima de aportación conjunta
    evt = service.emit_event(
        entity_type=SyncEntityType.CONTRIBUTION,
        action=SyncAction.UPSERT,
        payload={"month": "2026-11", "amount": 600.0, "contributor_profile": "MEMBER_A"},
    )
    assert evt.entity_type == SyncEntityType.CONTRIBUTION

    # Certificar que el schema rechaza entidades de finanzas privadas o arbitrarias
    with pytest.raises(Exception):
        service.emit_event(
            entity_type="PERSONAL_EXPENSE",  # type: ignore
            action=SyncAction.UPSERT,
            payload={"concept": "Cena privada con amigos"},
        )


def test_corrupted_json_handling(temp_sync_dir: str, db_session: Session):
    """Verifica que un archivo corrupto en inbox sea movido a error sin tumbar el procesamiento."""
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_A")

    corrupted_file = Path(temp_sync_dir) / "inbox" / "corrupted.json"
    with open(corrupted_file, "w", encoding="utf-8") as f:
        f.write("{ json_incompleto: ")

    res = service.process_inbox(db_session)
    assert res["error_count"] == 1
    assert not corrupted_file.exists()
    assert (Path(temp_sync_dir) / "error" / "corrupted.json").exists()


def test_skip_local_device_echo(temp_sync_dir: str, db_session: Session):
    """Verifica que los eventos generados por el mismo dispositivo sean archivados sin procesar."""
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_LOCAL")

    local_echo_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "PC_LOCAL",  # Mismo origen que el receptor
        "timestamp_utc": "2026-11-01T10:00:00Z",
        "payload": {"uuid": str(uuid.uuid4()), "amount": 20.0},
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_local.json", "w", encoding="utf-8") as f:
        json.dump(local_echo_evt, f)

    res = service.process_inbox(db_session)
    assert res["skipped_count"] == 1
    assert res["processed_count"] == 0
    assert not (Path(temp_sync_dir) / "inbox" / "evt_local.json").exists()


def test_get_sync_status(temp_sync_dir: str, db_session: Session):
    """Verifica el cálculo de deltas pendientes y estado de sincronización."""
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_A")

    # Estado limpio
    status = service.get_sync_status(db_session)
    assert status["is_synchronized"] is True
    assert status["outbox_pending_count"] == 0
    assert status["inbox_pending_count"] == 0

    # Emitir evento a outbox (el nodo sigue sincronizado porque inbox está vacío y no hay errores)
    service.emit_event(
        entity_type=SyncEntityType.CONTRIBUTION,
        action=SyncAction.UPSERT,
        payload={"month": "2026-11", "amount": 500.0},
    )
    status_pending = service.get_sync_status(db_session)
    assert status_pending["is_synchronized"] is True
    assert status_pending["outbox_pending_count"] == 1

    # Colocar evento pendiente en inbox: el nodo deja de estar sincronizado hasta procesarlo
    inbox_file = Path(temp_sync_dir) / "inbox" / "evt_pending.json"
    inbox_file.write_text("{}", encoding="utf-8")
    status_inbox = service.get_sync_status(db_session)
    assert status_inbox["is_synchronized"] is False
    assert status_inbox["inbox_pending_count"] == 1


def test_device_id_persistence_and_invitation_detection(temp_sync_dir: str):
    """Verifica que el identificador de dispositivo sea persistente y reconozca invitaciones."""
    temp_data_dir = Path(temp_sync_dir) / "data"
    from backend.services.joint_sync_service import get_or_create_device_id

    dev_id1 = get_or_create_device_id(temp_data_dir)
    assert dev_id1
    assert (temp_data_dir / "device_id.txt").exists()

    # Relectura debe retornar exactamente el mismo ID
    dev_id2 = get_or_create_device_id(temp_data_dir)
    assert dev_id1 == dev_id2

    # Invitación emitida por un dispositivo A hacia la bandeja de entrada de un dispositivo B
    service_b = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_EVITA")

    invitation_payload = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "ACCOUNT",
        "action": "UPSERT",
        "origin_device_id": "LOCAL_DEVICE",  # Origen heredado / remoto
        "timestamp_utc": "2026-11-02T16:00:00Z",
        "payload": {
            "household_name": "Vidita con Evita",
            "member_a_name": "Raúl",
            "member_b_name": "Evita",
            "cohabitation_stage": "PRE_COHABITATION",
            "split_mode": "EQUAL_50_50",
        },
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_account.json", "w", encoding="utf-8") as f:
        json.dump(invitation_payload, f)

    inv = service_b.get_pending_invitation()
    assert inv is not None
    assert inv["household_name"] == "Vidita con Evita"
    assert inv["member_a_name"] == "Raúl"


def test_cross_id_collision_name_resolution(temp_sync_dir: str, db_session: Session, setup_household_db: dict):
    """
    R-2: Certifica que la ingesta de transacciones resuelva prioritariamente por nombre
    descartando IDs autoincrementales discordantes entre dispositivos.
    """
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_USUARIO_B")

    # En este dispositivo B existen dos huchas:
    # ID 1: "Coche" (saldo 500 €)
    # ID 2: "Vacaciones" (saldo 1000 €)
    fund_coche = JointSinkingFund(
        joint_account_id=1,
        name="Coche",
        target_amount=3000.0,
        current_balance=500.0,
    )
    fund_vacaciones = JointSinkingFund(
        joint_account_id=1,
        name="Vacaciones",
        target_amount=2000.0,
        current_balance=1000.0,
    )
    db_session.add(fund_coche)
    db_session.add(fund_vacaciones)
    db_session.commit()
    db_session.refresh(fund_coche)
    db_session.refresh(fund_vacaciones)

    # Llega una transacción desde Dispositivo A imputada a "Vacaciones".
    # En Dispositivo A, "Vacaciones" tenía ID = 1 (el ID de Coche en B).
    tx_uuid = str(uuid.uuid4())
    evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "PC_USUARIO_A",
        "timestamp_utc": "2026-11-03T18:00:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-03",
            "amount": 200.0,
            "description": "Hotel Playa",
            "joint_sinking_fund_id": fund_coche.id,  # ID 1 en A
            "sinking_fund_name": "Vacaciones",       # Pero nombre es Vacaciones (ID 2 en B)
            "sinking_fund_deduction": 200.0,
        },
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_cross_id.json", "w", encoding="utf-8") as f:
        json.dump(evt, f)

    service.process_inbox(db_session)

    # La transacción debe haberse asignado a fund_vacaciones (ID 2), NO a fund_coche (ID 1)
    tx = db_session.query(JointTransaction).filter_by(uuid=tx_uuid).first()
    assert tx is not None
    assert tx.joint_sinking_fund_id == fund_vacaciones.id

    # El saldo de Vacaciones se redujo a 800 €, mientras que Coche permanece intacto en 500 €
    db_session.refresh(fund_vacaciones)
    db_session.refresh(fund_coche)
    assert fund_vacaciones.current_balance == 800.0
    assert fund_coche.current_balance == 500.0


def test_foreign_keys_pragma_and_sinking_fund_deletion(db_session: Session, setup_household_db: dict):
    """
    R-3: Certifica que al eliminar una hucha, las transacciones asociadas queden
    limpiamente desvinculadas (joint_sinking_fund_id = None) evitando huérfanos.
    """
    from backend.database.componentes.sqlite_crud import SQLiteRepository

    repo = SQLiteRepository(db_session)
    fund = JointSinkingFund(
        joint_account_id=1,
        name="Fondo Prueba Borrado",
        target_amount=1000.0,
        current_balance=200.0,
    )
    db_session.add(fund)
    db_session.commit()
    db_session.refresh(fund)

    tx = JointTransaction(
        uuid=str(uuid.uuid4()),
        joint_account_id=1,
        date=datetime.now(timezone.utc).date(),
        amount=50.0,
        description="Gasto prueba hucha",
        joint_sinking_fund_id=fund.id,
        created_by_profile="MEMBER_A",
    )
    db_session.add(tx)
    db_session.commit()
    db_session.refresh(tx)

    assert tx.joint_sinking_fund_id == fund.id

    # Eliminar hucha
    ok = repo.delete_joint_sinking_fund(fund.id)
    assert ok is True

    # La transacción debe seguir existiendo pero con joint_sinking_fund_id = None
    db_session.refresh(tx)
    assert tx.joint_sinking_fund_id is None


def test_contribution_uuid_and_multi_contribution_same_month(temp_sync_dir: str, db_session: Session, setup_household_db: dict):
    """
    R-5: Certifica que cada aportación tiene su UUID propio y que dos aportaciones en el
    mismo mes (ej. aportación regular + extraordinaria) coexisten sin sobreescribirse.
    """
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_RECEIVER")
    c1_uuid = str(uuid.uuid4())
    c2_uuid = str(uuid.uuid4())

    evt1 = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "CONTRIBUTION",
        "action": "UPSERT",
        "origin_device_id": "REMOTE_MAC",
        "timestamp_utc": "2026-11-01T10:00:00Z",
        "payload": {
            "uuid": c1_uuid,
            "month": "2026-11",
            "contributor_profile": "MEMBER_B",
            "amount": 500.0,
            "contribution_date": "2026-11-01",
        },
    }
    evt2 = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "CONTRIBUTION",
        "action": "UPSERT",
        "origin_device_id": "REMOTE_MAC",
        "timestamp_utc": "2026-11-15T12:00:00Z",
        "payload": {
            "uuid": c2_uuid,
            "month": "2026-11",
            "contributor_profile": "MEMBER_B",
            "amount": 250.0,
            "contribution_date": "2026-11-15",
        },
    }

    with open(Path(temp_sync_dir) / "inbox" / "evt_c1.json", "w", encoding="utf-8") as f:
        json.dump(evt1, f)
    with open(Path(temp_sync_dir) / "inbox" / "evt_c2.json", "w", encoding="utf-8") as f:
        json.dump(evt2, f)

    res = service.process_inbox(db_session)
    assert res["processed_count"] == 2

    # Ambas aportaciones deben coexistir en la base de datos
    c1 = db_session.query(JointMonthlyContribution).filter_by(uuid=c1_uuid).first()
    c2 = db_session.query(JointMonthlyContribution).filter_by(uuid=c2_uuid).first()
    assert c1 is not None
    assert c1.amount == 500.0
    assert c2 is not None
    assert c2.amount == 250.0

    # Si se envía un tombstone de c1, solo se borra c1, manteniendo c2 intacto
    evt_del = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "CONTRIBUTION",
        "action": "DELETE",
        "origin_device_id": "REMOTE_MAC",
        "timestamp_utc": "2026-11-20T10:00:00Z",
        "payload": {
            "uuid": c1_uuid,
            "month": "2026-11",
            "contributor_profile": "MEMBER_B",
        },
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_del_c1.json", "w", encoding="utf-8") as f:
        json.dump(evt_del, f)

    res_del = service.process_inbox(db_session)
    assert res_del["processed_count"] == 1
    assert db_session.query(JointMonthlyContribution).filter_by(uuid=c1_uuid).first() is None
    assert db_session.query(JointMonthlyContribution).filter_by(uuid=c2_uuid).first() is not None


def test_outbox_rotation(temp_sync_dir: str):
    """Verifica la rotación de outbox limitando el número de deltas viejos acumulados."""
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_ROTATION")

    # Emitir 6 eventos con rotación forzada a un máximo de 3
    for i in range(6):
        service.emit_event(
            entity_type=SyncEntityType.CONTRIBUTION,
            action=SyncAction.UPSERT,
            payload={"month": f"2026-0{i+1}", "amount": 100.0 * (i + 1)},
        )
        service.rotate_outbox(max_files=3)

    remaining_outbox = [f for f in service.outbox_dir.iterdir() if f.is_file() and f.suffix == ".json" and not f.name.endswith(".tmp")]
    assert len(remaining_outbox) == 3


def test_account_delete_remote_reset(temp_sync_dir: str, db_session: Session):
    """Verifica que un evento remoto ACCOUNT (DELETE) restablezca la base local a Estado Cero."""
    repo = SQLiteRepository(db_session)

    # Configurar cuenta local previa
    setup_req = JointAccountSetupRequest(
        household_name="Casa Test Reset Remoto",
        cohabitation_stage=CohabitationStage.PRE_COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.EQUAL_50_50,
        member_a_reference_income=2000.0,
        member_b_reference_income=2000.0,
        local_profile=ProfileIdentifier.MEMBER_B,
        remote_profile=ProfileIdentifier.MEMBER_A,
    )
    repo.create_joint_account(setup_req)
    assert repo.get_joint_account() is not None

    # Simular recepción de ACCOUNT (DELETE) desde el dispositivo de la pareja
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_RECEIVER")
    reset_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "ACCOUNT",
        "action": "DELETE",
        "origin_device_id": "PARTNER_PC",
        "timestamp_utc": "2026-11-20T12:00:00Z",
        "payload": {"household_name": "Casa Test Reset Remoto"},
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_reset.json", "w", encoding="utf-8") as f:
        json.dump(reset_evt, f)

    res = service.process_inbox(db_session)
    assert res["processed_count"] == 1
    # La cuenta ha sido reseteada al Estado Cero y no quedan eventos aplicados huérfanos
    assert repo.get_joint_account() is None
    assert db_session.query(JointAppliedSyncEvent).count() == 0


def test_subcategory_sync_upsert_and_delete(temp_sync_dir: str, db_session: Session):
    """Verifica que los eventos delta SUBCATEGORY (UPSERT/DELETE) creen, actualicen y eliminen subcategorías comunes."""
    repo = SQLiteRepository(db_session)

    # 1. Configurar cuenta local para tener las categorías sembradas
    setup_req = JointAccountSetupRequest(
        household_name="Casa Test Subcats",
        cohabitation_stage=CohabitationStage.COHABITATION,
        contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
        split_mode=SplitMode.EQUAL_50_50,
        member_a_reference_income=2500.0,
        member_b_reference_income=2500.0,
        local_profile=ProfileIdentifier.MEMBER_B,
        remote_profile=ProfileIdentifier.MEMBER_A,
    )
    repo.create_joint_account(setup_req)

    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="PC_RECEIVER")

    # 2. Recepción de SUBCATEGORY (UPSERT) para una nueva subcategoría
    subcat_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "SUBCATEGORY",
        "action": "UPSERT",
        "origin_device_id": "PARTNER_PC",
        "timestamp_utc": "2026-11-20T10:00:00Z",
        "payload": {
            "name": "Mascotas (Veterinario y Comida)",
            "monthly_budget": 85.0,
            "category_name": "Necesidades Básicas del Hogar",
        },
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_subcat_create.json", "w", encoding="utf-8") as f:
        json.dump(subcat_evt, f)

    res = service.process_inbox(db_session)
    assert res["processed_count"] == 1

    subcats = repo.get_joint_subcategories()
    mascotas = next((s for s in subcats if s.name == "Mascotas (Veterinario y Comida)"), None)
    assert mascotas is not None
    assert float(mascotas.monthly_budget) == 85.0

    # 3. Recepción de SUBCATEGORY (UPSERT) para actualizar el presupuesto
    update_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "SUBCATEGORY",
        "action": "UPSERT",
        "origin_device_id": "PARTNER_PC",
        "timestamp_utc": "2026-11-20T11:00:00Z",
        "payload": {
            "name": "Mascotas (Veterinario y Comida)",
            "monthly_budget": 120.0,
        },
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_subcat_update.json", "w", encoding="utf-8") as f:
        json.dump(update_evt, f)

    res_update = service.process_inbox(db_session)
    assert res_update["processed_count"] == 1

    db_session.refresh(mascotas)
    assert float(mascotas.monthly_budget) == 120.0

    # 4. Recepción de SUBCATEGORY (DELETE)
    del_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "SUBCATEGORY",
        "action": "DELETE",
        "origin_device_id": "PARTNER_PC",
        "timestamp_utc": "2026-11-20T12:00:00Z",
        "payload": {"name": "Mascotas (Veterinario y Comida)"},
    }
    with open(Path(temp_sync_dir) / "inbox" / "evt_subcat_del.json", "w", encoding="utf-8") as f:
        json.dump(del_evt, f)

    res_del = service.process_inbox(db_session)
    assert res_del["processed_count"] == 1

    subcats_after = repo.get_joint_subcategories()
    assert not any(s.name == "Mascotas (Veterinario y Comida)" for s in subcats_after)


def test_sync_events_detail_and_retry_errors(db_session: Session, temp_sync_dir: str):
    """
    Fase 7.2: Verifica la inspeccion de deltas en outbox, inbox, processed y error,
    asi como la recuperacion y reintento de eventos fallidos en cuarentena.
    """
    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="DEV_A")

    # 1. Crear evento valido en inbox
    inbox_path = Path(temp_sync_dir) / "inbox"
    evt_ok = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "SINKING_FUND",
        "action": "UPSERT",
        "origin_device_id": "DEV_B",
        "timestamp_utc": "2026-11-20T10:00:00Z",
        "payload": {
            "name": "Hucha Test Viewer",
            "target_amount": 500.0,
            "current_balance": 100.0,
            "monthly_target_amount": 50.0,
            "allocation_percentage": 10.0,
        },
    }
    with open(inbox_path / "evt_ok.json", "w", encoding="utf-8") as f:
        json.dump(evt_ok, f)

    # 2. Procesar inbox (va a processed/)
    service.process_inbox(db_session)

    # 3. Crear archivo erroneo en sync/error/
    error_path = Path(temp_sync_dir) / "error"
    with open(error_path / "bad_file.json", "w", encoding="utf-8") as f:
        f.write("{ invalid json")

    # 4. Consultar detalle de eventos
    details = service.get_sync_events_detail()
    assert details["inbox_count"] == 0
    assert details["processed_count"] >= 1
    assert details["error_count"] == 1
    assert len(details["processed_events"]) >= 1
    assert details["processed_events"][0]["entity_type"] == "SINKING_FUND"
    assert len(details["error_events"]) == 1
    assert "bad_file.json" in details["error_events"][0]["filename"]

    # 5. Reemplazar archivo de error por un delta corregido y reintentar
    fixed_evt = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "SINKING_FUND",
        "action": "UPSERT",
        "origin_device_id": "DEV_B",
        "timestamp_utc": "2026-11-20T10:05:00Z",
        "payload": {
            "name": "Hucha Recuperada",
            "target_amount": 1000.0,
            "current_balance": 200.0,
            "monthly_target_amount": 100.0,
            "allocation_percentage": 20.0,
        },
    }
    with open(error_path / "bad_file.json", "w", encoding="utf-8") as f:
        json.dump(fixed_evt, f)

    retry_res = service.retry_failed_events(db_session)
    assert retry_res["retried_count"] == 1
    assert retry_res["process_summary"]["processed_count"] == 1

    details_after = service.get_sync_events_detail()
    assert details_after["error_count"] == 0
    assert details_after["processed_count"] >= 2



def test_transaction_settlement_sync(temp_sync_dir: str, db_session: Session):
    """Verifica que los atributos de liquidación y reembolso de transacciones se propaguen y actualicen vía sync."""
    repo = SQLiteRepository(db_session)
    repo.create_joint_account(
        JointAccountSetupRequest(
            household_name="Hogar Settlement Sync",
            cohabitation_stage=CohabitationStage.COHABITATION,
            split_mode=SplitMode.EQUAL_50_50,
            contribution_strategy=ContributionStrategy.NOMINAL_TEMPLATE,
            member_a_reference_income=2500.0,
            member_b_reference_income=2200.0,
        )
    )

    service = JointSyncService(base_sync_dir=temp_sync_dir, local_device_id="DEV_LOCAL")
    inbox_path = Path(temp_sync_dir) / "inbox"
    tx_uuid = str(uuid.uuid4())

    # 1. Llega transacción adelantada por MEMBER_A en estado PENDING
    evt_pending = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "DEV_REMOTE",
        "timestamp_utc": "2026-11-04T10:00:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-04",
            "amount": 75.0,
            "description": "Ferretería bombillas",
            "subcategory_name": "Mantenimiento y Reparaciones del Hogar",
            "created_by_profile": "MEMBER_A",
            "paid_by": "MEMBER_A",
            "settlement_mechanism": "COMMON_REIMBURSEMENT",
            "settlement_status": "PENDING",
        },
    }
    with open(inbox_path / "evt_pending.json", "w", encoding="utf-8") as f:
        json.dump(evt_pending, f)

    res1 = service.process_inbox(db_session)
    assert res1["processed_count"] == 1

    tx_db = db_session.query(JointTransaction).filter_by(uuid=tx_uuid).first()
    assert tx_db is not None
    assert tx_db.paid_by == "MEMBER_A"
    assert tx_db.settlement_status == "PENDING"
    assert tx_db.settlement_mechanism == "COMMON_REIMBURSEMENT"

    # 2. Llega evento de liquidación con settlement_status=SETTLED
    evt_settled = {
        "event_id": str(uuid.uuid4()),
        "entity_type": "TRANSACTION",
        "action": "UPSERT",
        "origin_device_id": "DEV_REMOTE",
        "timestamp_utc": "2026-11-04T10:05:00Z",
        "payload": {
            "uuid": tx_uuid,
            "date": "2026-11-04",
            "amount": 75.0,
            "description": "Ferretería bombillas",
            "subcategory_name": "Mantenimiento y Reparaciones del Hogar",
            "created_by_profile": "MEMBER_A",
            "paid_by": "MEMBER_A",
            "settlement_mechanism": "COMMON_REIMBURSEMENT",
            "settlement_status": "SETTLED",
            "settled_at": "2026-11-04T10:05:00Z",
        },
    }
    with open(inbox_path / "evt_settled.json", "w", encoding="utf-8") as f:
        json.dump(evt_settled, f)

    res2 = service.process_inbox(db_session)
    assert res2["processed_count"] == 1

    db_session.refresh(tx_db)
    assert tx_db.settlement_status == "SETTLED"
    assert tx_db.settled_at is not None
