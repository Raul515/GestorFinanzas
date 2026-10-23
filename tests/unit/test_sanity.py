from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

def test_sanity_db_and_seed(db_session: Session, seed_data: dict[str, int]):
    """Verifica que el motor SQLite en memoria y la fixture seed_data funcionen con normalidad."""
    assert seed_data["cat_ingresos_id"] > 0
    assert seed_data["sub_emergencia_id"] > 0

def test_sanity_api_client(client: TestClient):
    """Verifica que el TestClient se comunique con la aplicación FastAPI con inyección de dependencias sobreescrita."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Gestor Finanzas API funcionando"}

