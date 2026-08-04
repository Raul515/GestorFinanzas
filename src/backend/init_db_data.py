import sys
import os

# Ensure backend package can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.componentes.sqlite_db import SessionLocal, init_db
from backend.domain.models import categorias as cat_model

def populate():
    init_db()
    db = SessionLocal()
    
    # Check if data exists
    if db.query(cat_model.Categoria).first():
        print("La base de datos ya contiene datos.")
        db.close()
        return

    print("Poblando datos iniciales según Excel...")
    
    cats = [
        {"nombre": "Ingresos Netos", "tipo": "ingreso"},
        {"nombre": "Necesidades Básicas", "tipo": "gasto"},
        {"nombre": "Deseos y Estilo de vida", "tipo": "gasto"},
        {"nombre": "Ahorro e Inversión", "tipo": "ahorro"}
    ]
    
    db_cats = []
    for c in cats:
        db_c = cat_model.Categoria(nombre=c["nombre"], tipo=c["tipo"])
        db.add(db_c)
        db_cats.append(db_c)
    db.commit()
    
    # Subcategorias
    ingresos = ["Salario NETO", "Ingresos Secundarios", "Devoluciones y Reembolsos", "Intereses y Dividendos", "Otros Ingresos"]
    necesidades = ["Alquiler / Hipoteca", "Suministros (Luz, agua, gas, internet)", "Alimentación básica", "Seguros (Salud, Coche, Vida)", "Cuota del Coche", "Gasolina y Transporte público", "Pago de Deudas (Préstamos personales, mínimos de Tarjetas de Crédito)", "Otros Gastos Esenciales"]
    deseos = ["Entretenimiento (Tomar algo...)", "Salir a comer fuera", "Gimnasio", "Hobbies (Libros, cursos libres)", "Ropa y Complementos", "Tecnología y Dispositivos", "Fondo para Viajes y Vacaciones", "Cuidado Personal (Peluquería, estética, masajes)", "Suscripciones plataformas (Netflix, Spotiffly…)", "Otros Caprichos"]
    ahorro = ["Fondo de emergencia", "Inversión Largo Plazo (Fondos Indexados)", "Fondo de amortización para Proyectos (Medio Plazo)", "Fondo de amortizacion para x (Corto Plazo)"]

    subs_map = {
        "Ingresos Netos": ingresos,
        "Necesidades Básicas": necesidades,
        "Deseos y Estilo de vida": deseos,
        "Ahorro e Inversión": ahorro
    }

    for db_c in db_cats:
        for s_name in subs_map[db_c.nombre]:
            db_s = cat_model.Subcategoria(nombre=s_name, categoria_id=db_c.id)
            db.add(db_s)
    
    db.commit()
    db.close()
    print("Datos iniciales insertados con éxito.")

if __name__ == "__main__":
    populate()
