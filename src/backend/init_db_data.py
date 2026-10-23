import sys
import os

# Asegurar que el paquete backend pueda ser importado
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.componentes.sqlite_db import SessionLocal, init_db
from backend.domain.models import categories as cat_model


def populate():
    """Inicializa la base de datos y puebla las categorías y subcategorías iniciales si está vacía."""
    init_db()
    db = SessionLocal()

    # Comprobar si ya existen datos en la base de datos
    if db.query(cat_model.Category).first():
        print("La base de datos ya contiene datos.")
        db.close()
        return

    print("Poblando datos iniciales según Excel...")

    cats = [
        {"name": "Ingresos Netos", "type": "ingreso"},
        {"name": "Necesidades Básicas", "type": "gasto"},
        {"name": "Deseos y Estilo de vida", "type": "gasto"},
        {"name": "Ahorro e Inversión", "type": "ahorro"},
    ]

    db_cats = []
    for c in cats:
        db_c = cat_model.Category(name=c["name"], type=c["type"])
        db.add(db_c)
        db_cats.append(db_c)
    db.commit()

    # Subcategorías (etiquetas de interfaz en español, columnas en inglés)

    ingresos = [
        "Salario NETO",
        "Ingresos Secundarios",
        "Devoluciones y Reembolsos",
        "Intereses y Dividendos",
        "Otros Ingresos",
    ]
    necesidades = [
        "Alquiler / Hipoteca",
        "Suministros (Luz, agua, gas, internet)",
        "Alimentación básica",
        "Seguros (Salud, Coche, Vida)",
        "Cuota del Coche",
        "Gasolina y Transporte público",
        "Pago de Deudas (Préstamos personales, mínimos de Tarjetas de Crédito)",
        "Otros Gastos Esenciales",
    ]
    deseos = [
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
    ]
    ahorro = [
        "Fondo de emergencia",
        "Inversión Largo Plazo (Fondos Indexados)",
        "Fondo de amortización para Proyectos (Medio Plazo)",
        "Fondo de amortizacion para x (Corto Plazo)",
    ]

    subs_map = {
        "Ingresos Netos": ingresos,
        "Necesidades Básicas": necesidades,
        "Deseos y Estilo de vida": deseos,
        "Ahorro e Inversión": ahorro,
    }

    for db_c in db_cats:
        for s_name in subs_map[db_c.name]:
            db_s = cat_model.Subcategory(name=s_name, category_id=db_c.id)
            db.add(db_s)

    db.commit()
    db.close()
    print("Datos iniciales insertados con éxito.")


if __name__ == "__main__":
    populate()
