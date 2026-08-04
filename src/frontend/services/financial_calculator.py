"""
Financial Calculator Service.
Contiene funciones puras para el cálculo de flujo financiero, 
totales mensuales, regla 50/30/20 y resúmenes anuales.
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
    ahorro_name: str
) -> Dict[str, Dict[str, Any]]:
    """Calcula el presupuesto y gasto real por categoría y subcategoría para un mes."""
    totales_m: Dict[str, Dict[str, Any]] = {}
    
    for cat in categorias:
        cat_subcats = [s for s in todas_subcats if s['categoria_id'] == cat['id']]
        t_pres = 0.0
        t_real = 0.0
        
        for s in cat_subcats:
            s_id = s['id']
            pval = 0.0
            if presupuestos_m:
                p_match = [p for p in presupuestos_m if p['subcategoria_id'] == s_id]
                if p_match:
                    pval = p_match[0]['cantidad']
            t_pres += pval
            
            tval = 0.0
            if transacciones_m:
                r_match = [t['cantidad'] for t in transacciones_m if t['subcategoria_id'] == s_id]
                tval = sum(r_match)
            
            t_real += (pval + tval)
            
        totales_m[cat['nombre']] = {
            "presupuesto": t_pres,
            "real": t_real,
            "tipo": cat['tipo'],
            "subcategorias": cat_subcats
        }
    
    # Derivar automáticamente presupuestos de bloques según regla 50/30/20 sobre ingresos presupuestados
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
    real_aho: float
) -> Tuple[float, float, float, float, float]:
    """
    Calcula los porcentajes reales de cada bloque respecto a los ingresos reales del mes,
    así como el monto y porcentaje del bloque 'Sin Asignar'.
    Retorna: (pct_nec, pct_des, pct_aho, pct_sin, real_sin_asignar)
    """
    real_sin_asignar = max(0.0, real_ing - (real_nec + real_des + real_aho))
    if real_ing > 0:
        pct_nec = (real_nec / real_ing) * 100
        pct_des = (real_des / real_ing) * 100
        pct_aho = (real_aho / real_ing) * 100
        pct_sin = (real_sin_asignar / real_ing) * 100
    else:
        pct_nec, pct_des, pct_aho, pct_sin = 0.0, 0.0, 0.0, 0.0
        
    return pct_nec, pct_des, pct_aho, pct_sin, real_sin_asignar

def calculate_annual_metrics(
    anual_data: Dict[int, Dict[str, Dict[str, float]]],
    ingresos_name: str,
    necesidades_name: str,
    deseos_name: str,
    ahorro_name: str
) -> Dict[str, float]:
    """Calcula totales acumulados anuales para la vista de resumen."""
    ingresos_anual_real = sum(anual_data[m][ingresos_name]["real"] for m in range(1, 13))
    nec_anual_real = sum(anual_data[m][necesidades_name]["real"] for m in range(1, 13))
    des_anual_real = sum(anual_data[m][deseos_name]["real"] for m in range(1, 13))
    aho_anual_real = sum(anual_data[m][ahorro_name]["real"] for m in range(1, 13))
    
    gastos_anual_real = nec_anual_real + des_anual_real + aho_anual_real
    ahorro_acumulado_total = ingresos_anual_real - gastos_anual_real
    
    pct_nec_real = (nec_anual_real / ingresos_anual_real * 100) if ingresos_anual_real > 0 else 0.0
    pct_des_real = (des_anual_real / ingresos_anual_real * 100) if ingresos_anual_real > 0 else 0.0
    pct_aho_real = (aho_anual_real / ingresos_anual_real * 100) if ingresos_anual_real > 0 else 0.0
    
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
        "desv_aho": pct_aho_real - 20.0
    }
