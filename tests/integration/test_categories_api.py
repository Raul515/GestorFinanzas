import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.domain.models import categories as cat_models
from backend.domain.models import budgets as budget_models
from backend.domain.models import transactions as trans_models
from backend.domain.models import joint as joint_models


def test_get_categories_api(client: TestClient, seed_data: dict[str, int]):
    """Verifica que el endpoint GET /categories/ devuelva el catálogo con subcategorías anidadas."""
    response = client.get("/categories/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4
    necesidades = next((c for c in data if c["id"] == seed_data["cat_necesidades_id"]), None)
    assert necesidades is not None
    assert len(necesidades["subcategories"]) > 0


def test_create_subcategory_api(client: TestClient, seed_data: dict[str, int]):
    """Verifica la creación de una nueva subcategoría mediante POST /categories/subcategories/."""
    payload = {
        "name": "Suscripción Spotify y Música",
        "category_id": seed_data["cat_deseos_id"],
    }
    response = client.post("/categories/subcategories/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == "Suscripción Spotify y Música"
    assert data["category_id"] == seed_data["cat_deseos_id"]


def test_get_subcategory_usage_api(client: TestClient, seed_data: dict[str, int]):
    """Verifica la consulta de uso de una subcategoría mediante GET /categories/subcategories/{id}/usage."""
    sub_id = seed_data["sub_alquiler_id"]
    response = client.get(f"/categories/subcategories/{sub_id}/usage")
    assert response.status_code == 200
    data = response.json()
    assert data["subcategory_id"] == sub_id
    assert "transactions_count" in data
    assert "budgets_count" in data
    assert "can_delete" in data


def test_update_subcategory_api_success(client: TestClient, seed_data: dict[str, int]):
    """Verifica el renombrado exitoso de una subcategoría personalizada mediante PUT /categories/subcategories/{id}."""
    create_res = client.post(
        "/categories/subcategories/",
        json={"name": "Clases de Canto", "category_id": seed_data["cat_deseos_id"]},
    )
    sub_id = create_res.json()["id"]
    response = client.put(f"/categories/subcategories/{sub_id}", json={"name": "Clases de Canto y Voz"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sub_id
    assert data["name"] == "Clases de Canto y Voz"


def test_update_subcategory_api_not_found(client: TestClient):
    """Verifica error 404 al intentar actualizar una subcategoría inexistente."""
    response = client.put("/categories/subcategories/99999", json={"name": "No Existe"})
    assert response.status_code == 404
    assert "no encontrada" in response.json()["detail"].lower()


def test_update_subcategory_api_empty_name(client: TestClient, seed_data: dict[str, int]):
    """Verifica error 400 al enviar un nombre vacío o con espacios."""
    sub_id = seed_data["sub_alquiler_id"]
    response = client.put(f"/categories/subcategories/{sub_id}", json={"name": "   "})
    assert response.status_code == 400
    assert "no puede estar vacío" in response.json()["detail"].lower()


def test_delete_subcategory_api_success(client: TestClient, seed_data: dict[str, int]):
    """Verifica la eliminación física exitosa de una subcategoría sin dependencias."""
    create_res = client.post(
        "/categories/subcategories/",
        json={"name": "Temporal Borrable", "category_id": seed_data["cat_deseos_id"]},
    )
    assert create_res.status_code == 200
    sub_id = create_res.json()["id"]

    del_res = client.delete(f"/categories/subcategories/{sub_id}")
    assert del_res.status_code == 200
    assert del_res.json() == {"deleted": True, "subcategory_id": sub_id}

    del_res_again = client.delete(f"/categories/subcategories/{sub_id}")
    assert del_res_again.status_code == 404


def test_delete_subcategory_api_conflict_with_transactions(client: TestClient, db_session: Session, seed_data: dict[str, int]):
    """Verifica que el endpoint devuelva HTTP 409 Conflict si la subcategoría tiene transacciones registradas."""
    create_res = client.post(
        "/categories/subcategories/",
        json={"name": "Restaurantes y Cenas", "category_id": seed_data["cat_deseos_id"]},
    )
    sub_id = create_res.json()["id"]

    tx = trans_models.Transaction(
        date=datetime.date(2026, 11, 4),
        subcategory_id=sub_id,
        amount=42.50,
        description="Cena amigos",
    )
    db_session.add(tx)
    db_session.commit()

    del_res = client.delete(f"/categories/subcategories/{sub_id}")
    assert del_res.status_code == 409
    error_detail = del_res.json()["detail"]
    assert "No se puede eliminar la subcategoría" in error_detail
    assert "1 transacciones" in error_detail


def test_delete_subcategory_api_success_with_budgets(client: TestClient, db_session: Session, seed_data: dict[str, int]):
    """Verifica que el endpoint permita eliminar una subcategoría con presupuesto si tiene 0 transacciones."""
    create_res = client.post(
        "/categories/subcategories/",
        json={"name": "Gas Natural Extra", "category_id": seed_data["cat_necesidades_id"]},
    )
    sub_id = create_res.json()["id"]

    budget = budget_models.MonthlyBudget(
        month="BASE",
        subcategory_id=sub_id,
        amount=60.0,
    )
    db_session.add(budget)
    db_session.commit()

    del_res = client.delete(f"/categories/subcategories/{sub_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Verificar que el presupuesto fue purgado
    found_b = db_session.query(budget_models.MonthlyBudget).filter_by(subcategory_id=sub_id).first()
    assert found_b is None


def test_base_subcategory_protection_api(client: TestClient, seed_data: dict[str, int]):
    """Verifica que la API rechace renombrar o eliminar subcategorías base del sistema."""
    base_id = seed_data["sub_alquiler_id"]

    # Intento de renombrar
    ren_res = client.put(f"/categories/subcategories/{base_id}", json={"name": "Alquiler Ilegal"})
    assert ren_res.status_code == 400
    assert "No se puede modificar el nombre de la subcategoría base" in ren_res.json()["detail"]

    # Intento de eliminar
    del_res = client.delete(f"/categories/subcategories/{base_id}")
    assert del_res.status_code == 409
    assert "No se puede eliminar una subcategoría base" in del_res.json()["detail"]


def test_joint_subcategories_api_usage_and_delete(client: TestClient, db_session: Session):
    """Verifica consulta de uso y eliminación protegida de subcategorías de hogar mediante /joint/subcategories/."""
    account = joint_models.JointAccount(
        household_name="Casa Test API",
        member_a_name="A",
        member_b_name="B",
        member_a_reference_income=1500.0,
        member_b_reference_income=1500.0,
        split_mode="EQUAL_50_50",
        cohabitation_stage="COHABITATION",
    )
    db_session.add(account)
    db_session.flush()

    cat = joint_models.JointCategory(
        joint_account_id=account.id,
        name="Suministros Hogar"
    )
    db_session.add(cat)
    db_session.commit()

    create_res = client.post("/joint/subcategories", json={
        "name": "Fibra Óptica 1Gbps",
        "joint_category_id": cat.id,
        "monthly_budget": 35.0,
    })
    assert create_res.status_code == 201
    subcat_data = create_res.json()
    sub_id = subcat_data["id"]

    usage_res = client.get(f"/joint/subcategories/{sub_id}/usage")
    assert usage_res.status_code == 200
    assert usage_res.json()["can_delete"] is True
    assert usage_res.json()["transactions_count"] == 0

    tx = joint_models.JointTransaction(
        joint_account_id=account.id,
        date=datetime.date(2026, 11, 4),
        description="Factura internet",
        amount=35.0,
        paid_by="MEMBER_A",
        created_by_profile="MEMBER_A",
        joint_subcategory_id=sub_id,
    )
    db_session.add(tx)
    db_session.commit()

    usage_res2 = client.get(f"/joint/subcategories/{sub_id}/usage")
    assert usage_res2.status_code == 200
    assert usage_res2.json()["can_delete"] is False
    assert usage_res2.json()["transactions_count"] == 1

    del_res_blocked = client.delete(f"/joint/subcategories/{sub_id}")
    assert del_res_blocked.status_code == 409
    assert "transacciones del hogar vinculadas" in del_res_blocked.json()["detail"].lower()

    db_session.delete(tx)
    db_session.commit()

    del_res_ok = client.delete(f"/joint/subcategories/{sub_id}")
    assert del_res_ok.status_code == 200
    assert del_res_ok.json()["deleted"] is True

    del_res_404 = client.delete(f"/joint/subcategories/{sub_id}")
    assert del_res_404.status_code == 404


def test_create_subcategory_duplicate_api(client: TestClient, seed_data: dict[str, int]):
    """Verifica que la API retorne HTTP 409 Conflict al intentar crear una subcategoría duplicada."""
    payload = {"name": "Gimnasio Crossfit", "category_id": seed_data["cat_deseos_id"]}
    res1 = client.post("/categories/subcategories/", json=payload)
    assert res1.status_code == 200

    # Segundo intento con diferente capitalización
    payload_dup = {"name": "gimnasio crossfit", "category_id": seed_data["cat_deseos_id"]}
    res2 = client.post("/categories/subcategories/", json=payload_dup)
    assert res2.status_code == 409
    assert "Ya existe una subcategoría" in res2.json()["detail"]


def test_create_joint_subcategory_duplicate_api(client: TestClient, db_session: Session):
    """Verifica que la API retorne HTTP 409 Conflict al registrar una subcategoría conjunta duplicada."""
    account = joint_models.JointAccount(
        household_name="Hogar Dup API",
        cohabitation_stage="COHABITATION",
    )
    db_session.add(account)
    cat = joint_models.JointCategory(joint_account_id=1, name="Hogar")
    db_session.add(cat)
    db_session.commit()

    res1 = client.post("/joint/subcategories", json={
        "name": "Supermercado Semanal",
        "joint_category_id": cat.id,
        "monthly_budget": 200.0,
    })
    assert res1.status_code == 201

    res2 = client.post("/joint/subcategories", json={
        "name": "supermercado semanal",
        "joint_category_id": cat.id,
        "monthly_budget": 250.0,
    })
    assert res2.status_code == 409
    assert "Ya existe una subcategoría" in res2.json()["detail"]


def test_create_joint_subcategory_pre_cohabitation_blocked_api(client: TestClient, db_session: Session):
    """Verifica que en Pre-Convivencia la API bloquee con 400 Bad Request el alta de subcategorías comunes."""
    account = joint_models.JointAccount(
        household_name="Hogar Pre API",
        cohabitation_stage="PRE_COHABITATION",
    )
    db_session.add(account)
    cat = joint_models.JointCategory(joint_account_id=1, name="Hogar")
    db_session.add(cat)
    db_session.commit()

    res = client.post("/joint/subcategories", json={
        "name": "Alquiler Piso",
        "joint_category_id": cat.id,
        "monthly_budget": 700.0,
    })
    assert res.status_code == 400
    assert "Pre-Convivencia" in res.json()["detail"]
