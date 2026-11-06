"""
Constantes contables y del dominio financiero del sistema.
Define las subcategorías oficiales y base sembradas por defecto en el perfil personal y la cuenta conjunta.
"""

from typing import List

DEFAULT_PERSONAL_SUBCATEGORIES: List[str] = [
    # Ingresos
    "Salario NETO",
    "Ingresos Secundarios",
    "Devoluciones y Reembolsos",
    "Intereses y Dividendos",
    "Reintegros por Cierres de Huchas Conjuntas",
    "Otros Ingresos",
    # Necesidades Básicas
    "Alquiler / Hipoteca",
    "Suministros (Luz, agua, gas, internet)",
    "Alimentación básica",
    "Seguros (Salud, Coche, Vida)",
    "Cuota del Coche",
    "Gasolina y Transporte público",
    "Pago de Deudas (Préstamos personales, mínimos de Tarjetas de Crédito)",
    "Otros Gastos Esenciales",
    # Deseos y Estilo de vida
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
    # Ahorro e Inversión
    "Fondo de emergencia",
    "Inversión Largo Plazo (Fondos Indexados)",
    "Fondo de amortización para Proyectos (Medio Plazo)",
    "Fondo de amortizacion para x (Corto Plazo)",
]

DEFAULT_JOINT_SUBCATEGORIES: List[str] = [
    "Vivienda (Alquiler / Hipoteca)",
    "Suministros (Luz, Agua, Gas, Internet)",
    "Alimentación y Supermercado",
    "Comunidad y Seguros del Hogar",
]


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

