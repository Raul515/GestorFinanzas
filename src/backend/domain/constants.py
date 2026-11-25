"""
Constantes contables y del dominio financiero del sistema.
Define el catálogo oficial, clasificación canónica de bloques 50/30/20
y claves compartidas de caché.
"""

from enum import Enum
from typing import Any, Dict, List, Optional


class CategoryBlock(str, Enum):
    """Bloques contables canónicos del método 50/30/20 e ingresos."""

    INCOME = "INCOME"
    NEEDS = "NEEDS"
    WANTS = "WANTS"
    SAVINGS = "SAVINGS"


CANONICAL_CATEGORY_NAMES: Dict[CategoryBlock, str] = {
    CategoryBlock.INCOME: "Ingresos Netos",
    CategoryBlock.NEEDS: "Necesidades Básicas",
    CategoryBlock.WANTS: "Deseos y Estilo de vida",
    CategoryBlock.SAVINGS: "Ahorro e Inversión",
}

CACHE_KEY_MACRO_INDICATORS = "macro_indicators"
CACHE_KEY_MACRO_NEWS = "macro_news"

PERSONAL_CATEGORY_CATALOG: List[Dict[str, Any]] = [
    {
        "block": CategoryBlock.INCOME,
        "name": "Ingresos Netos",
        "type": "ingreso",
        "subcategories": [
            "Salario NETO",
            "Ingresos Secundarios",
            "Devoluciones y Reembolsos",
            "Intereses y Dividendos",
            "Reintegros por Cierres de Huchas Conjuntas",
            "Otros Ingresos",
        ],
    },
    {
        "block": CategoryBlock.NEEDS,
        "name": "Necesidades Básicas",
        "type": "gasto",
        "subcategories": [
            "Alquiler / Hipoteca",
            "Suministros (Luz, agua, gas, internet)",
            "Alimentación básica",
            "Seguros (Salud, Coche, Vida)",
            "Cuota del Coche",
            "Gasolina y Transporte público",
            "Pago de Deudas (Préstamos personales, mínimos de Tarjetas de Crédito)",
            "Otros Gastos Esenciales",
        ],
    },
    {
        "block": CategoryBlock.WANTS,
        "name": "Deseos y Estilo de vida",
        "type": "gasto",
        "subcategories": [
            "Entretenimiento (Tomar algo...)",
            "Salir a comer fuera",
            "Gimnasio",
            "Hobbies (Libros, cursos libres)",
            "Ropa y Complementos",
            "Tecnología y Dispositivos",
            "Fondo para Viajes y Vacaciones",
            "Cuidado Personal (Peluquería, estética, masajes)",
            "Suscripciones plataformas (Netflix, Spotiffly…)",
            "Otros Caprichos",
        ],
    },
    {
        "block": CategoryBlock.SAVINGS,
        "name": "Ahorro e Inversión",
        "type": "ahorro",
        "subcategories": [
            "Fondo de emergencia",
            "Inversión Largo Plazo (Fondos Indexados)",
            "Fondo de amortización para Proyectos (Medio Plazo)",
            "Fondo de amortizacion para x (Corto Plazo)",
        ],
    },
]

DEFAULT_PERSONAL_SUBCATEGORIES: List[str] = [
    sub for entry in PERSONAL_CATEGORY_CATALOG for sub in entry["subcategories"]
]

DEFAULT_JOINT_SUBCATEGORIES: List[str] = [
    "Vivienda (Alquiler / Hipoteca)",
    "Suministros (Luz, Agua, Gas, Internet)",
    "Alimentación y Supermercado",
    "Comunidad y Seguros del Hogar",
]


def classify_category_block(
    category_or_name: Any,
    category_type: Optional[str] = None,
) -> Optional[CategoryBlock]:
    """
    Clasifica de forma canónica una categoría (modelo ORM, dict o nombre)
    en su bloque 50/30/20 o de ingresos.
    """
    if category_or_name is None and not category_type:
        return None

    if isinstance(category_or_name, str):
        c_name = category_or_name
        c_type = category_type or ""
    elif isinstance(category_or_name, dict):
        c_name = str(category_or_name.get("nombre") or category_or_name.get("name") or "")
        c_type = str(category_or_name.get("tipo") or category_or_name.get("type") or category_type or "")
    else:
        c_name = str(getattr(category_or_name, "name", "") or "")
        c_type = str(getattr(category_or_name, "type", "") or category_type or "")

    t_low = c_type.strip().lower()
    n_low = c_name.strip().lower()

    if t_low in ("income", "ingreso") or "ingreso" in n_low or "income" in n_low:
        return CategoryBlock.INCOME
    if "necesidad" in n_low or "50%" in n_low or "needs" in n_low:
        return CategoryBlock.NEEDS
    if t_low in ("ahorro", "savings") or "ahorro" in n_low or "20%" in n_low or "invers" in n_low or "saving" in n_low:
        return CategoryBlock.SAVINGS
    if "deseo" in n_low or "30%" in n_low or "wants" in n_low or "ocio" in n_low:
        return CategoryBlock.WANTS
    return None


def is_income_category(category_or_name: Any, category_type: Optional[str] = None) -> bool:
    """Determina de forma uniforme si una categoría representa ingresos."""
    return classify_category_block(category_or_name, category_type) == CategoryBlock.INCOME


def is_emergency_fund_subcategory(subcategory_or_name: Any) -> bool:
    """Determina si una subcategoría corresponde al Fondo de Emergencia."""
    if isinstance(subcategory_or_name, str):
        name = subcategory_or_name
    elif isinstance(subcategory_or_name, dict):
        name = str(subcategory_or_name.get("nombre") or subcategory_or_name.get("name") or "")
    else:
        name = str(getattr(subcategory_or_name, "name", "") or "")
    return "emergencia" in name.strip().lower()


def is_default_personal_subcategory(name: str) -> bool:
    """Indica si una subcategoría pertenece al catálogo base inicial del perfil personal."""
    if not name:
        return False
    norm = name.strip().lower()
    return any(norm == base.strip().lower() for base in DEFAULT_PERSONAL_SUBCATEGORIES)


def is_default_joint_subcategory(name: str) -> bool:
    """Indica si una subcategoría pertenece al catálogo base inicial de la cuenta conjunta."""
    if not name:
        return False
    norm = name.strip().lower()
    return any(norm == base.strip().lower() for base in DEFAULT_JOINT_SUBCATEGORIES)

