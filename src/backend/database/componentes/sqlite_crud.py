from sqlalchemy.orm import Session
from sqlalchemy import extract
from backend.database.interfaz.db_interface import IRepository
from backend.domain.models import (
    categorias as cat_model,
    presupuestos as pres_model,
    transacciones as trans_model,
    emergency_fund as fund_model,
    market_cache as cache_model,
)
from backend.domain.schemas import categorias as cat_schema, presupuestos as pres_schema, transacciones as trans_schema
from typing import Optional, Any
import json
import datetime

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

        # Sync EmergencyFund current_balance if transaction belongs to 'Fondo de emergencia'
        subcat = self.db.query(cat_model.Subcategoria).filter(cat_model.Subcategoria.id == db_item.subcategoria_id).first()
        if subcat and "fondo de emergencia" in subcat.nombre.lower():
            self.adjust_emergency_fund_balance(db_item.cantidad)

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
        if not presupuestos:
            return []

        es_base = any(item.mes == "BASE" for item in presupuestos)
        if es_base:
            # 1. Congelar automáticamente los meses pasados reales antes de actualizar la plantilla BASE
            today = datetime.date.today()
            mes_actual_str = today.strftime("%Y-%m")
            year_actual = today.year
            
            # Obtener la plantilla BASE antigua que existía hasta este momento
            base_antiguo = self.db.query(pres_model.PresupuestoMensual).filter(pres_model.PresupuestoMensual.mes == "BASE").all()
            
            if base_antiguo:
                # Congelar meses pasados del año actual (ej. 2026-01 a 2026-07)
                for m in range(1, today.month):
                    m_key = f"{year_actual}-{m:02d}"
                    if m_key < mes_actual_str:
                        tiene_especifico = self.db.query(pres_model.PresupuestoMensual).filter(pres_model.PresupuestoMensual.mes == m_key).first()
                        if not tiene_especifico:
                            for b in base_antiguo:
                                p_congelado = pres_model.PresupuestoMensual(
                                    mes=m_key,
                                    subcategoria_id=b.subcategoria_id,
                                    cantidad=b.cantidad
                                )
                                self.db.add(p_congelado)
                self.db.commit()

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

    def get_or_create_emergency_fund(self) -> fund_model.EmergencyFund:
        fund = self.db.query(fund_model.EmergencyFund).first()
        if not fund:
            fund = fund_model.EmergencyFund(
                current_balance=0.0,
                target_months=3,
                target_amount=0.0,
                is_completed=False,
            )
            self.db.add(fund)
            self.db.commit()
            self.db.refresh(fund)
        return fund

    def update_emergency_fund(
        self,
        target_months: Optional[int] = None,
        current_balance: Optional[float] = None,
    ) -> fund_model.EmergencyFund:
        fund = self.get_or_create_emergency_fund()
        if target_months is not None:
            if target_months < 3:
                raise ValueError("El número de meses de cobertura no puede ser inferior a 3 (regla constitucional).")
            fund.target_months = target_months
        if current_balance is not None:
            fund.current_balance = max(0.0, current_balance)
        self.db.commit()
        self.db.refresh(fund)
        return fund

    def adjust_emergency_fund_balance(self, delta: float) -> fund_model.EmergencyFund:
        fund = self.get_or_create_emergency_fund()
        fund.current_balance = max(0.0, fund.current_balance + delta)
        self.db.commit()
        self.db.refresh(fund)
        return fund

    def get_market_cache(self, key: str) -> Optional[dict]:
        entry = (
            self.db.query(cache_model.MarketCache)
            .filter(cache_model.MarketCache.key == key)
            .first()
        )
        if not entry:
            return None
        # Verify expiration
        now = datetime.datetime.now()
        if entry.expires_at and entry.expires_at < now:
            return None
        try:
            return json.loads(entry.data_json)
        except Exception:
            return None

    def set_market_cache(
        self, key: str, data: Any, ttl_hours: int = 24
    ) -> cache_model.MarketCache:
        now = datetime.datetime.now()
        expires_at = now + datetime.timedelta(hours=ttl_hours)
        data_json = json.dumps(data, ensure_ascii=False, default=str)

        entry = (
            self.db.query(cache_model.MarketCache)
            .filter(cache_model.MarketCache.key == key)
            .first()
        )
        if entry:
            entry.data_json = data_json
            entry.updated_at = now
            entry.expires_at = expires_at
        else:
            entry = cache_model.MarketCache(
                key=key,
                data_json=data_json,
                updated_at=now,
                expires_at=expires_at,
            )
            self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def invalidate_market_cache(self, key: Optional[str] = None) -> None:
        if key:
            self.db.query(cache_model.MarketCache).filter(
                cache_model.MarketCache.key == key
            ).delete()
        else:
            self.db.query(cache_model.MarketCache).delete()
        self.db.commit()
