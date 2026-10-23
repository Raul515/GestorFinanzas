from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

def test_sanity_db_and_seed(db_session: Session, seed_data: dict[str, int]):
    """Verifies that in-memory SQLite and seed_data fixture work cleanly."""
    assert seed_data["cat_ingresos_id"] > 0
    assert seed_data["sub_emergencia_id"] > 0

def test_sanity_api_client(client: TestClient):
    """Verifies that TestClient connects to FastAPI app with dependency override."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Gestor Finanzas API funcionando"}
