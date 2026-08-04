from sqlalchemy.orm import Session
from sqlalchemy import extract
from backend.database.interfaz.db_interface import IRepository
from backend.domain.models import categorias as cat_model, presupuestos as pres_model, transacciones as trans_model
from backend.domain.schemas import categorias as cat_schema, presupuestos as pres_schema, transacciones as trans_schema
from typing import Optional

class SQLiteRepository(IRepository):
    def __init__(self, db: Session):
        self.db = db

    def get_categorias(self):
        return self.db.query(cat_model.Categoria).all()

    def create_categoria(self, categoria: cat_schema.CategoriaCreate):
        db_item = cat_model.Categoria(**categoria.model_dump())
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def get_subcategorias(self, categoria_id: Optional[int] = None):
        query = self.db.query(cat_model.Subcategoria)
        if categoria_id:
            query = query.filter(cat_model.Subcategoria.categoria_id == categoria_id)
        return query.all()

    def create_subcategoria(self, subcategoria: cat_schema.SubcategoriaCreate):
        db_item = cat_model.Subcategoria(**subcategoria.model_dump())
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def get_transacciones(self, mes: Optional[str] = None):
        query = self.db.query(trans_model.Transaccion)
        if mes:
            year, month = map(int, mes.split('-'))
            query = query.filter(
                extract('year', trans_model.Transaccion.fecha) == year,
                extract('month', trans_model.Transaccion.fecha) == month
            )
        return query.all()

    def create_transaccion(self, transaccion: trans_schema.TransaccionCreate):
        db_item = trans_model.Transaccion(**transaccion.model_dump())
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def get_presupuestos(self, mes: str):
        return self.db.query(pres_model.PresupuestoMensual).filter(pres_model.PresupuestoMensual.mes == mes).all()

    def create_presupuesto(self, presupuesto: pres_schema.PresupuestoMensualCreate):
        db_item = pres_model.PresupuestoMensual(**presupuesto.model_dump())
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item
