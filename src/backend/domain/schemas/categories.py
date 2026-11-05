from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class SubcategoryBase(BaseModel):
    """Esquema base de subcategoría contable."""
    name: str


class SubcategoryCreate(SubcategoryBase):
    """Esquema para creación de nueva subcategoría vinculada a una categoría padre."""
    category_id: int


class SubcategoryUpdate(BaseModel):
    """Esquema para actualización del nombre de una subcategoría."""
    name: str


class SubcategoryUsage(BaseModel):
    """Esquema con auditoría de uso de una subcategoría en transacciones y presupuestos."""
    subcategory_id: int
    transactions_count: int
    budgets_count: int
    can_delete: bool
    is_base: bool = False


class Subcategory(SubcategoryBase):
    """Esquema de respuesta para subcategoría persistida."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int


class CategoryBase(BaseModel):
    """Esquema base para categorías contables principales."""
    name: str
    type: str


class CategoryCreate(CategoryBase):
    """Esquema para creación de una categoría principal."""
    pass


class Category(CategoryBase):
    """Esquema de respuesta para categoría contable persistida con sus subcategorías."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    subcategories: List[Subcategory] = []
