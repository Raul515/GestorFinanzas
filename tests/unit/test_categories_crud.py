import datetime
import pytest
from sqlalchemy.orm import Session

from backend.database.componentes.sqlite_crud import SQLiteRepository
from backend.domain.models import categories as cat_models
from backend.domain.models import budgets as budget_models
from backend.domain.models import transactions as trans_models
from backend.domain.models import joint as joint_models
from backend.domain.schemas import categories as cat_schemas
from backend.domain.schemas import joint as joint_schemas
from backend.init_db_data import populate


def test_create_and_read_subcategory(db_session: Session, seed_data: dict[str, int]):
    """Verifica la persistencia y lectura de una nueva subcategoría personal."""
    repo = SQLiteRepository(db_session)
    cat_id = seed_data["cat_necesidades_id"]

    sub_create = cat_schemas.SubcategoryCreate(name="Farmacia y Medicamentos", category_id=cat_id)
    created = repo.create_subcategory(sub_create)

    assert created.id is not None
    assert created.name == "Farmacia y Medicamentos"
    assert created.category_id == cat_id

    subcats = repo.get_subcategories(category_id=cat_id)
    names = [s.name for s in subcats]
    assert "Farmacia y Medicamentos" in names


def test_update_subcategory_success(db_session: Session, seed_data: dict[str, int]):
    """Verifica que se pueda renombrar una subcategoría personalizada existente."""
    repo = SQLiteRepository(db_session)
    custom_sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Clases de Piano",
        category_id=seed_data["cat_deseos_id"]
    ))

    updated = repo.update_subcategory(custom_sub.id, "Clases de Teclado")
    assert updated is not None
    assert updated.id == custom_sub.id
    assert updated.name == "Clases de Teclado"

    subcats = repo.get_subcategories()
    found = next((s for s in subcats if s.id == custom_sub.id), None)
    assert found is not None
    assert found.name == "Clases de Teclado"


def test_update_subcategory_not_found(db_session: Session):
    """Verifica que renombrar una subcategoría inexistente retorne None."""
    repo = SQLiteRepository(db_session)
    result = repo.update_subcategory(99999, "Nombre Fantasma")
    assert result is None


def test_update_subcategory_empty_name(db_session: Session, seed_data: dict[str, int]):
    """Verifica que se rechace un nombre vacío o con puros espacios en blanco."""
    repo = SQLiteRepository(db_session)
    sub_id = seed_data["sub_alquiler_id"]

    with pytest.raises(ValueError, match="El nombre de la subcategoría no puede estar vacío"):
        repo.update_subcategory(sub_id, "   ")


def test_check_subcategory_usage_empty(db_session: Session, seed_data: dict[str, int]):
    """Verifica que una subcategoría recién creada sin datos reporte uso en cero y can_delete=True."""
    repo = SQLiteRepository(db_session)
    sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Clases de Guitarra",
        category_id=seed_data["cat_deseos_id"]
    ))

    usage = repo.check_subcategory_usage(sub.id)
    assert usage["subcategory_id"] == sub.id
    assert usage["transactions_count"] == 0
    assert usage["budgets_count"] == 0
    assert usage["can_delete"] is True


def test_check_subcategory_usage_with_transactions(db_session: Session, seed_data: dict[str, int]):
    """Verifica que si existen transacciones vinculadas, can_delete sea False."""
    repo = SQLiteRepository(db_session)
    sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Veterinario",
        category_id=seed_data["cat_necesidades_id"]
    ))

    tx = trans_models.Transaction(
        date=datetime.date(2026, 11, 1),
        subcategory_id=sub.id,
        amount=65.0,
        description="Vacuna perro",
    )
    db_session.add(tx)
    db_session.commit()

    usage = repo.check_subcategory_usage(sub.id)
    assert usage["transactions_count"] == 1
    assert usage["budgets_count"] == 0
    assert usage["can_delete"] is False


def test_check_subcategory_usage_with_budgets(db_session: Session, seed_data: dict[str, int]):
    """Verifica que si existen asignaciones en MonthlyBudget pero 0 transacciones, can_delete sea True (limpieza en cascada)."""
    repo = SQLiteRepository(db_session)
    sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Cursos Online",
        category_id=seed_data["cat_deseos_id"]
    ))

    budget = budget_models.MonthlyBudget(
        month="BASE",
        subcategory_id=sub.id,
        amount=50.0,
    )
    db_session.add(budget)
    db_session.commit()

    usage = repo.check_subcategory_usage(sub.id)
    assert usage["transactions_count"] == 0
    assert usage["budgets_count"] == 1
    assert usage["can_delete"] is True


def test_delete_subcategory_with_budgets_cascades(db_session: Session, seed_data: dict[str, int]):
    """Verifica que eliminar una subcategoría sin transacciones elimine en cascada sus presupuestos asociados."""
    repo = SQLiteRepository(db_session)
    sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Clases de Baile",
        category_id=seed_data["cat_deseos_id"]
    ))

    budget = budget_models.MonthlyBudget(
        month="BASE",
        subcategory_id=sub.id,
        amount=40.0,
    )
    db_session.add(budget)
    db_session.commit()

    deleted = repo.delete_subcategory(sub.id)
    assert deleted is True

    # Verificar que el presupuesto huérfano fue purgado
    rem_budget = db_session.query(budget_models.MonthlyBudget).filter_by(subcategory_id=sub.id).first()
    assert rem_budget is None


def test_base_subcategory_protection_crud(db_session: Session, seed_data: dict[str, int]):
    """Verifica que las subcategorías base del sistema estén blindadas contra renombrado y borrado."""
    repo = SQLiteRepository(db_session)
    base_id = seed_data["sub_alquiler_id"]

    # Bloqueo de renombrado
    with pytest.raises(ValueError, match="No se puede modificar el nombre de la subcategoría base del sistema"):
        repo.update_subcategory(base_id, "Hipoteca Modificada")

    # Bloqueo de eliminación
    with pytest.raises(ValueError, match="No se puede eliminar la subcategoría base del sistema"):
        repo.delete_subcategory(base_id)


def test_joint_base_subcategory_protection_crud(db_session: Session):
    """Verifica que las subcategorías base del hogar estén blindadas contra renombrado y borrado."""
    repo = SQLiteRepository(db_session)
    account = repo.create_joint_account(
        joint_schemas.JointAccountSetupRequest(
            household_name="Hogar Test Protegido",
            cohabitation_stage=joint_schemas.CohabitationStage.COHABITATION,
            split_mode=joint_schemas.SplitMode.EQUAL_50_50,
            contribution_strategy=joint_schemas.ContributionStrategy.NOMINAL_TEMPLATE,
            member_a_reference_income=2500.0,
            member_b_reference_income=2200.0,
        )
    )
    base_subcat = repo.get_joint_subcategories()[0]

    # Bloqueo de renombrado
    with pytest.raises(ValueError, match="No se puede modificar el nombre de la subcategoría base del hogar"):
        repo.update_joint_subcategory(base_subcat.id, joint_schemas.JointSubcategoryUpdate(name="Nombre No Permitido"))

    # Bloqueo de eliminación
    with pytest.raises(ValueError, match="No se puede eliminar la subcategoría base del hogar"):
        repo.delete_joint_subcategory(base_subcat.id)


def test_delete_subcategory_success(db_session: Session, seed_data: dict[str, int]):
    """Verifica la eliminación física de una subcategoría limpia."""
    repo = SQLiteRepository(db_session)
    sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Temporal Para Borrar",
        category_id=seed_data["cat_deseos_id"]
    ))
    sub_id = sub.id

    deleted = repo.delete_subcategory(sub_id)
    assert deleted is True

    found = db_session.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == sub_id).first()
    assert found is None


def test_delete_subcategory_blocked_with_dependencies(db_session: Session, seed_data: dict[str, int]):
    """Verifica que se lance ValueError al intentar eliminar una subcategoría con transacciones o presupuestos."""
    repo = SQLiteRepository(db_session)
    sub = repo.create_subcategory(cat_schemas.SubcategoryCreate(
        name="Gasto Bloqueado",
        category_id=seed_data["cat_deseos_id"]
    ))

    tx = trans_models.Transaction(
        date=datetime.date(2026, 11, 2),
        subcategory_id=sub.id,
        amount=25.0,
        description="Gasto de prueba",
    )
    db_session.add(tx)
    db_session.commit()

    with pytest.raises(ValueError, match="No se puede eliminar la subcategoría 'Gasto Bloqueado'"):
        repo.delete_subcategory(sub.id)

    remaining = db_session.query(cat_models.Subcategory).filter(cat_models.Subcategory.id == sub.id).first()
    assert remaining is not None


def test_delete_subcategory_not_found(db_session: Session):
    """Verifica que delete_subcategory retorne False si el ID no existe."""
    repo = SQLiteRepository(db_session)
    assert repo.delete_subcategory(99999) is False


def test_joint_subcategory_crud_and_usage(db_session: Session):
    """Verifica alta, auditoría de uso, bloqueo de borrado y eliminación en subcategorías conjuntas."""
    repo = SQLiteRepository(db_session)

    account = joint_models.JointAccount(
        household_name="Hogar Test",
        member_a_name="Raúl",
        member_b_name="Pareja",
        member_a_reference_income=2000.0,
        member_b_reference_income=2000.0,
        split_mode="EQUAL_50_50",
        cohabitation_stage="COHABITATION",
    )
    db_session.add(account)
    db_session.flush()

    cat = joint_models.JointCategory(
        joint_account_id=account.id,
        name="Gastos del Hogar",
    )
    db_session.add(cat)
    db_session.flush()

    subcat_create = joint_schemas.JointSubcategoryCreate(
        name="Mascotas y Comida Gato",
        joint_category_id=cat.id,
        monthly_budget=80.0,
    )
    subcat = repo.create_joint_subcategory(subcat_create)
    assert subcat.id is not None
    assert subcat.name == "Mascotas y Comida Gato"

    usage = repo.check_joint_subcategory_usage(subcat.id)
    assert usage["transactions_count"] == 0
    assert usage["can_delete"] is True

    tx = joint_models.JointTransaction(
        joint_account_id=account.id,
        date=datetime.date(2026, 11, 3),
        description="Pienso esterilizado",
        amount=45.0,
        paid_by="MEMBER_A",
        created_by_profile="MEMBER_A",
        joint_subcategory_id=subcat.id,
    )
    db_session.add(tx)
    db_session.commit()

    usage_with_tx = repo.check_joint_subcategory_usage(subcat.id)
    assert usage_with_tx["transactions_count"] == 1
    assert usage_with_tx["can_delete"] is False

    with pytest.raises(ValueError, match="No se puede eliminar la subcategoría conjunta"):
        repo.delete_joint_subcategory(subcat.id)

    db_session.delete(tx)
    db_session.commit()

    deleted = repo.delete_joint_subcategory(subcat.id)
    assert deleted is True
    assert repo.get_joint_subcategory(subcat.id) is None


def test_init_db_data_preserves_custom_subcategories(db_session: Session):
    """Verifica que el sembrado idempotente de populate() respete y preserve las subcategorías personalizadas."""
    cat = cat_models.Category(name="Deseos y Estilo de vida", type="gasto")
    db_session.add(cat)
    db_session.flush()

    custom_sub = cat_models.Subcategory(name="Cómics y Manga", category_id=cat.id)
    db_session.add(custom_sub)
    db_session.commit()

    populate()

    found = db_session.query(cat_models.Subcategory).filter(cat_models.Subcategory.name == "Cómics y Manga").first()
    assert found is not None
    assert found.category_id == cat.id


def test_create_subcategory_duplicate_rejected(db_session: Session, seed_data: dict[str, int]):
    """Verifica que no se permita crear subcategorías duplicadas case-insensitive en la misma categoría."""
    repo = SQLiteRepository(db_session)
    cat_id = seed_data["cat_necesidades_id"]

    repo.create_subcategory(cat_schemas.SubcategoryCreate(name="BBS", category_id=cat_id))

    with pytest.raises(ValueError, match="Ya existe una subcategoría con el nombre 'bbs'"):
        repo.create_subcategory(cat_schemas.SubcategoryCreate(name="bbs", category_id=cat_id))


def test_create_joint_subcategory_duplicate_rejected(db_session: Session):
    """Verifica que no se permita crear subcategorías conjuntas duplicadas case-insensitive."""
    repo = SQLiteRepository(db_session)
    account = joint_models.JointAccount(
        household_name="Casa Duplicados",
        cohabitation_stage="COHABITATION",
    )
    db_session.add(account)
    cat = joint_models.JointCategory(joint_account_id=1, name="Común")
    db_session.add(cat)
    db_session.commit()

    repo.create_joint_subcategory(joint_schemas.JointSubcategoryCreate(
        name="Artículos Limpieza",
        joint_category_id=cat.id,
        monthly_budget=20.0
    ))

    with pytest.raises(ValueError, match="Ya existe una subcategoría con el nombre 'artículos limpieza'"):
        repo.create_joint_subcategory(joint_schemas.JointSubcategoryCreate(
            name="artículos limpieza",
            joint_category_id=cat.id,
            monthly_budget=25.0
        ))


def test_create_joint_subcategory_blocked_in_pre_cohabitation(db_session: Session):
    """Verifica que no se permita dar de alta necesidades comunes si la cuenta está en Pre-Convivencia."""
    repo = SQLiteRepository(db_session)
    account = joint_models.JointAccount(
        household_name="Casa Pre",
        cohabitation_stage="PRE_COHABITATION",
    )
    db_session.add(account)
    cat = joint_models.JointCategory(joint_account_id=1, name="Común")
    db_session.add(cat)
    db_session.commit()

    with pytest.raises(ValueError, match="etapa de Pre-Convivencia"):
        repo.create_joint_subcategory(joint_schemas.JointSubcategoryCreate(
            name="Luz y Gas",
            joint_category_id=cat.id,
            monthly_budget=50.0
        ))
