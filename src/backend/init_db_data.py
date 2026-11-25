import sys
import os

# Asegurar que el paquete backend pueda ser importado
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.componentes.sqlite_db import SessionLocal, init_db
from backend.domain.constants import PERSONAL_CATEGORY_CATALOG
from backend.domain.models import categories as cat_model


def populate():
    """Inicializa la base de datos y puebla las categorías y subcategorías iniciales si está vacía."""
    init_db()
    try:
        from backend.services.joint_sync_service import JointSyncService
        JointSyncService()
    except Exception as exc:
        print(f"Aviso inicializando carpetas de sincronización: {exc}")

    db = SessionLocal()
    print("Verificando sembrado inicial idempotente de categorías...")

    for entry in PERSONAL_CATEGORY_CATALOG:
        db_c = db.query(cat_model.Category).filter(cat_model.Category.name == entry["name"]).first()
        if not db_c:
            db_c = cat_model.Category(name=entry["name"], type=entry["type"])
            db.add(db_c)
            db.commit()
            db.refresh(db_c)

        for s_name in entry["subcategories"]:
            db_s = db.query(cat_model.Subcategory).filter(
                cat_model.Subcategory.name == s_name,
                cat_model.Subcategory.category_id == db_c.id
            ).first()
            if not db_s:
                db_s = cat_model.Subcategory(name=s_name, category_id=db_c.id)
                db.add(db_s)

    db.commit()
    db.close()
    print("Sembrado idempotente completado con éxito.")


if __name__ == "__main__":
    populate()
