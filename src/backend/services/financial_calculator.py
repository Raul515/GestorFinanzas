"""
Servicio de Cálculo Financiero (Servicio de Dominio del Backend).
Contiene funciones puras para la lógica de presupuesto 50/30/20,
totales mensuales por categoría, seguimiento del fondo 'Sin Asignar' y consolidación anual.
Desacoplado por completo de la capa de presentación.
"""

from typing import Dict, List, Any, Tuple


def calculate_category_totals(
    categorias: List[Dict[str, Any]],
    todas_subcats: List[Dict[str, Any]],
    presupuestos_m: List[Dict[str, Any]],
    transacciones_m: List[Dict[str, Any]],
    ingresos_name: str,
    necesidades_name: str,
    deseos_name: str,
    ahorro_name: str,
) -> Dict[str, Dict[str, Any]]:
    """Calcula los importes presupuestados y reales por categoría y subcategoría para un mes determinado."""
    totales_m: Dict[str, Dict[str, Any]] = {}

    for cat in categorias:
        cat_id = cat.get("id")
        cat_subcats = [
            s for s in todas_subcats 
            if (s.get("categoria_id") if s.get("categoria_id") is not None else s.get("category_id")) == cat_id
        ]
        t_pres = 0.0
        t_real = 0.0

        for s in cat_subcats:
            s_id = s.get("id")
            pval = 0.0
            if presupuestos_m:
                p_match = [
                    p for p in presupuestos_m 
                    if (p.get("subcategoria_id") if p.get("subcategoria_id") is not None else p.get("subcategory_id")) == s_id
                ]
                if p_match:
                    pval = float(p_match[0].get("cantidad") or p_match[0].get("amount") or 0.0)
            t_pres += pval

            tval = 0.0
            if transacciones_m:
                r_match: List[float] = [
                    float(t.get("cantidad") or t.get("amount") or 0.0)
                    for t in transacciones_m 
                    if (t.get("subcategoria_id") if t.get("subcategoria_id") is not None else t.get("subcategory_id")) == s_id
                ]
                tval = sum(r_match)

            t_real += (pval + tval)

        c_name = cat.get("nombre") or cat.get("name", "")
        c_type = cat.get("tipo") or cat.get("type", "")
        totales_m[c_name] = {
            "presupuesto": t_pres,
            "real": t_real,
            "tipo": c_type,
            "subcategorias": cat_subcats,
        }

    # Derivar los topes presupuestarios 50/30/20 a partir del ingreso neto presupuestado
    pres_ing = totales_m.get(ingresos_name, {}).get("presupuesto", 0.0)
    if necesidades_name in totales_m:
        totales_m[necesidades_name]["presupuesto"] = pres_ing * 0.50
    if deseos_name in totales_m:
        totales_m[deseos_name]["presupuesto"] = pres_ing * 0.30
    if ahorro_name in totales_m:
        totales_m[ahorro_name]["presupuesto"] = pres_ing * 0.20

    return totales_m


def calculate_503020_percentages(
    real_ing: float,
    real_nec: float,
    real_des: float,
    real_aho: float,
) -> Tuple[float, float, float, float, float]:
    """
    Calcula la distribución porcentual real de los bloques 50/30/20 en relación al ingreso real,
    así como el importe y porcentaje del excedente 'Sin Asignar'.
    Retorna: (pct_nec, pct_des, pct_aho, pct_sin, real_sin_asignar)
    """
    real_sin_asignar = max(0.0, real_ing - (real_nec + real_des + real_aho))
    if real_ing > 0.0:
        pct_nec = (real_nec / real_ing) * 100.0
        pct_des = (real_des / real_ing) * 100.0
        pct_aho = (real_aho / real_ing) * 100.0
        pct_sin = (real_sin_asignar / real_ing) * 100.0
    else:
        pct_nec, pct_des, pct_aho, pct_sin = 0.0, 0.0, 0.0, 0.0

    return pct_nec, pct_des, pct_aho, pct_sin, real_sin_asignar


def calculate_annual_metrics(
    anual_data: Dict[int, Dict[str, Dict[str, float]]],
    ingresos_name: str,
    necesidades_name: str,
    deseos_name: str,
    ahorro_name: str,
) -> Dict[str, float]:
    """Calcula totales acumulados anuales, ahorro total y desviaciones frente a la regla 50/30/20."""
    ingresos_anual_real = sum(anual_data[m][ingresos_name]["real"] for m in range(1, 13))
    nec_anual_real = sum(anual_data[m][necesidades_name]["real"] for m in range(1, 13))
    des_anual_real = sum(anual_data[m][deseos_name]["real"] for m in range(1, 13))
    aho_anual_real = sum(anual_data[m][ahorro_name]["real"] for m in range(1, 13))

    gastos_anual_real = nec_anual_real + des_anual_real + aho_anual_real
    ahorro_acumulado_total = ingresos_anual_real - gastos_anual_real

    pct_nec_real = (nec_anual_real / ingresos_anual_real * 100.0) if ingresos_anual_real > 0.0 else 0.0
    pct_des_real = (des_anual_real / ingresos_anual_real * 100.0) if ingresos_anual_real > 0.0 else 0.0
    pct_aho_real = (aho_anual_real / ingresos_anual_real * 100.0) if ingresos_anual_real > 0.0 else 0.0

    return {
        "ingresos_anual_real": ingresos_anual_real,
        "nec_anual_real": nec_anual_real,
        "des_anual_real": des_anual_real,
        "aho_anual_real": aho_anual_real,
        "gastos_anual_real": gastos_anual_real,
        "ahorro_acumulado_total": ahorro_acumulado_total,
        "pct_nec_real": pct_nec_real,
        "pct_des_real": pct_des_real,
        "pct_aho_real": pct_aho_real,
        "desv_nec": pct_nec_real - 50.0,
        "desv_des": pct_des_real - 30.0,
        "desv_aho": pct_aho_real - 20.0,
    }


def get_monthly_needs_budget(
    presupuestos: List[Dict[str, Any]],
    subcategorias: List[Dict[str, Any]],
    categoria_necesidades_id: int,
) -> float:
    """
    Extrae el total presupuestado en Necesidades Básicas para un mes determinado o plantilla BASE.
    Filtra las subcategorías correspondientes a categoria_necesidades_id.
    """
    nec_subcat_ids = {
        s["id"] for s in subcategorias 
        if (s.get("categoria_id") if s.get("categoria_id") is not None else s.get("category_id")) == categoria_necesidades_id
    }
    total_needs = 0.0
    for p in presupuestos:
        sub_id = p.get("subcategoria_id") if p.get("subcategoria_id") is not None else p.get("subcategory_id")
        if sub_id in nec_subcat_ids:
            raw_val = p.get("cantidad") or p.get("amount") or 0.0
            total_needs += float(raw_val)
    return total_needs

