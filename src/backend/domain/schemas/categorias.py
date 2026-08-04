from pydantic import BaseModel
from typing import List, Optional

class SubcategoriaBase(BaseModel):
    nombre: str

class SubcategoriaCreate(SubcategoriaBase):
    categoria_id: int

class Subcategoria(SubcategoriaBase):
    id: int
    categoria_id: int

    class Config:
        from_attributes = True

class CategoriaBase(BaseModel):
    nombre: str
    tipo: str

class CategoriaCreate(CategoriaBase):
    pass

class Categoria(CategoriaBase):
    id: int
    subcategorias: List[Subcategoria] = []

    class Config:
        from_attributes = True
