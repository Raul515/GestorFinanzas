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
        especificos = self.db.query(pres_model.PresupuestoMensual).filter(pres_model.PresupuestoMensual.mes == mes).all()
        if mes == "BASE" or especificos:
            return especificos
        
        # Fallback: si no hay presupuestos específicos para este mes, devolver la plantilla BASE
        base_list = self.db.query(pres_model.PresupuestoMensual).filter(pres_model.PresupuestoMensual.mes == "BASE").all()
        resultado = []
        for b in base_list:
            resultado.append(pres_model.PresupuestoMensual(id=0, mes=mes, subcategoria_id=b.subcategoria_id, cantidad=b.cantidad))
        return resultado

    def create_presupuesto(self, presupuesto: pres_schema.PresupuestoMensualCreate):
        # Upsert por (mes, subcategoria_id)
        db_item = self.db.query(pres_model.PresupuestoMensual).filter(
            pres_model.PresupuestoMensual.mes == presupuesto.mes,
            pres_model.PresupuestoMensual.subcategoria_id == presupuesto.subcategoria_id
        ).first()
        
        if db_item:
            db_item.cantidad = presupuesto.cantidad
        else:
            db_item = pres_model.PresupuestoMensual(**presupuesto.model_dump())
            self.db.add(db_item)
            
        self.db.commit()
        self.db.refresh(db_item)
        return db_item

    def save_presupuestos_bulk(self, presupuestos: list[pres_schema.PresupuestoMensualCreate]):
        resultado = []
        for item in presupuestos:
            db_item = self.db.query(pres_model.PresupuestoMensual).filter(
                pres_model.PresupuestoMensual.mes == item.mes,
                pres_model.PresupuestoMensual.subcategoria_id == item.subcategoria_id
            ).first()
            
            if db_item:
                db_item.cantidad = item.cantidad
            else:
                db_item = pres_model.PresupuestoMensual(**item.model_dump())
                self.db.add(db_item)
            self.db.commit()
            self.db.refresh(db_item)
            resultado.append(db_item)
        return resultado
