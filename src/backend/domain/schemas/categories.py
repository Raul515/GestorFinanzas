from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class SubcategoryBase(BaseModel):
    """Esquema base de subcategoría contable."""
    name: str


class SubcategoryCreate(SubcategoryBase):
    """Esquema para creación de nueva subcategoría vinculada a una categoría padre."""
    category_id: int


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

