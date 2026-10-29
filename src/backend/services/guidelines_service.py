"""
Servicio de Pautas Deterministas de Gestión y Compensación Presupuestaria (Spec 008).
Implementa la lógica pura de evaluación financiera, jerarquías de absorción presupuestaria,
estrategias de distribución con cifras reales y diagnósticos estructurales para meses individuales
y el resumen anual bajo la regla 50/30/20 y la Constitución del proyecto.
"""

from typing import Any, Dict, List, Optional

from backend.domain.schemas.guidelines import (
    AnnualGuidelineItem,
    AnnualGuidelineReport,
    AnnualScenarioType,
    CompensationStep,
    GuidelineActionStrategy,
    GuidelineSeverity,
    MonthlyGuidelineItem,
    MonthlyGuidelineReport,
    MonthlyScenarioType,
    SynopticTableRow,
)


def evaluate_monthly_guidelines(
    month_key: str,
    month_name: str,
    real_income: float,
    budget_income: float,
    real_needs: float,
    real_wants: float,
    real_savings: float,
    safety_status: Optional[Dict[str, Any]] = None,
) -> MonthlyGuidelineReport:
    """
    Evalúa el estado financiero de un mes individual y genera las pautas deterministas correspondientes,
    calculando importes exactos en euros, estrategias de redistribución y tablas sinópticas.
    """
    target_needs = 0.50 * real_income if real_income > 0 else 0.0
    target_wants = 0.30 * real_income if real_income > 0 else 0.0
    target_savings = 0.20 * real_income if real_income > 0 else 0.0

    total_spent = real_needs + real_wants + real_savings
    unassigned_amount = max(0.0, real_income - total_spent)
    savings_rate = (real_savings / real_income * 100.0) if real_income > 0 else 0.0

    cov_months = float(safety_status.get("coverage_months", 0.0)) if safety_status else 0.0
    tgt_months = float(safety_status.get("target_months", 3.0)) if safety_status else 3.0
    is_ef_completed = bool(safety_status.get("is_completed", False)) if safety_status else False
    ef_gap = float(safety_status.get("gap", 0.0)) if safety_status else 0.0

    guidelines: List[MonthlyGuidelineItem] = []
    synoptic_table: List[SynopticTableRow] = []

    # 1. CASO 1: EXCEDENTE EN NECESIDADES BÁSICAS (real_needs < target_needs)
    if real_income > 0 and real_needs < target_needs:
        surplus = target_needs - real_needs
        delta_pct = (surplus / real_income * 100.0)

        ef_breakdown_step1 = (
            f"Fase 1 (Fondo en Construcción): Se suman los {surplus:,.2f} € a tu ahorro base y van directos a tu "
            f"Fondo de Emergencia (faltan {ef_gap:,.2f} € para la meta de {tgt_months:.0f} meses)."
            if not is_ef_completed
            else (
                f"Fondo Blindado ({cov_months:.1f} meses cubiertos): Los {surplus:,.2f} € van al 100% directos a "
                f"inversión a largo plazo (fondos indexados globales de acumulación)."
            )
        )
        ef_breakdown_step2 = (
            "Fase 2 (Una vez blindado): El 100% de los excedentes futuros se canalizará a inversión a largo plazo."
            if not is_ef_completed
            else "Resultado: Multiplicas la velocidad del interés compuesto y acortas el tiempo hacia la Libertad Financiera (FIRE)."
        )

        strat_fire = GuidelineActionStrategy(
            name="Estrategia 1: El Acelerador FIRE (Inyección Pura a Ahorro e Inversión)",
            badge="Opción Principal",
            allocation_amount=round(surplus, 2),
            description="Derivar el 100% del excedente a fortalecer tu bloque de futuro sin inflar los Deseos.",
            breakdown_items=[ef_breakdown_step1, ef_breakdown_step2],
        )

        strat_sinking = GuidelineActionStrategy(
            name="Estrategia 2: Creación de Objetivos / Provisión a Medio Plazo (Ahorro con Propósito)",
            badge="Sinking Fund",
            allocation_amount=round(surplus, 2),
            description="Dividir el excedente para metas futuras específicas a 3-5 años sin tocar la renta variable.",
            breakdown_items=[
                f"Fondo de Proyectos / Amortización ({surplus * 0.5:,.2f} €): Para activos previstos a medio plazo (coche, vivienda, reformas) en cuenta remunerada o depósito.",
                f"Inversión Pura Indexada ({surplus * 0.5:,.2f} €): Aportación periódica a cartera indexada para el largo plazo.",
            ],
        )

        strat_hybrid = GuidelineActionStrategy(
            name="Estrategia 3: El Enfoque Híbrido / Regla del Bonus (80/20)",
            badge="Equilibrio Consciente",
            allocation_amount=round(surplus, 2),
            description="Premiar la disciplina personal permitiendo un pequeño disfrute sin descapitalizar el futuro.",
            breakdown_items=[
                f"80% ({surplus * 0.8:,.2f} €) a Ahorro e Inversión: Potencias tu patrimonio neto con disciplina.",
                f"20% ({surplus * 0.2:,.2f} €) a Deseos: Aumentas ligeramente ocio o viajes de forma consciente sin caer en el derroche.",
            ],
        )

        syn_row1 = SynopticTableRow(
            scenario_name="Excedente en Necesidades (Fijo)",
            funding_source="100% a Ahorro/Inversión (Fondo de Emergencia o Bolsa)",
            touch_emergency_fund="NO (Al revés: se usa el excedente para rellenarlo si falta)",
            budget_action="Asignar según Acelerador FIRE o Regla 80/20",
        )

        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.NEEDS_SURPLUS,
                severity=GuidelineSeverity.INFO,
                title=f"Excedente Positivo en Necesidades Básicas (+{surplus:,.2f} € / +{delta_pct:.1f}%)",
                summary_headline=(
                    f"Tus necesidades reales ({real_needs:,.2f} €) son inferiores al 50% presupuestado ({target_needs:,.2f} €), "
                    f"generando un excedente de {surplus:,.2f} €. Regla de oro: este sobrante jamás debe derivarse por defecto a aumentar los Deseos."
                ),
                delta_amount=round(surplus, 2),
                delta_percentage=round(delta_pct, 2),
                strategies=[strat_fire, strat_sinking, strat_hybrid],
                synoptic_row=syn_row1,
                emergency_fund_rule="NO se retira. Si el fondo no cubre la meta, el excedente debe emplearse prioritariamente en completarlo.",
                key_recommendation="Aplica el Acelerador FIRE: canaliza el 100% del sobrante a blindar el Fondo de Emergencia o a inversión indexada.",
            )
        )
        synoptic_table.append(syn_row1)

    # 2. CASO 2: DÉFICIT EN NECESIDADES BÁSICAS (real_needs > target_needs)
    if real_income > 0 and real_needs > target_needs:
        excess_nec = real_needs - target_needs
        delta_pct_nec = (excess_nec / real_income * 100.0)

        step1_amount = min(excess_nec, real_wants)
        step2_amount = max(0.0, excess_nec - real_wants)

        steps_nec: List[CompensationStep] = [
            CompensationStep(
                priority=1,
                source_block="Deseos (30%)",
                amount=round(step1_amount, 2),
                action_text=f"Primera línea de defensa: Reducir temporalmente ocio, restaurantes o caprichos en hasta {step1_amount:,.2f} € este mes.",
                can_touch_emergency_fund=False,
            ),
            CompensationStep(
                priority=2,
                source_block="Ahorro del mes (20%)",
                amount=round(step2_amount, 2),
                action_text=(
                    f"Segunda línea de defensa: Si el bloque de Deseos no basta, absorber los {step2_amount:,.2f} € restantes reduciendo "
                    f"la tasa de ahorro del mes."
                    if step2_amount > 0
                    else "Segunda línea de defensa: No requerida este mes (cubierto con Deseos)."
                ),
                can_touch_emergency_fund=False,
            ),
            CompensationStep(
                priority=3,
                source_block="Fondo de Emergencia",
                amount=round(excess_nec, 2),
                action_text="Únicamente si los gastos provienen de una catástrofe, avería grave indispensable para trabajar o urgencia médica.",
                can_touch_emergency_fund=True,
            ),
        ]

        syn_row2 = SynopticTableRow(
            scenario_name="Pico en Necesidades (Fijo)",
            funding_source="1º Del bloque de Deseos (30%), 2º Del Ahorro del mes (20%)",
            touch_emergency_fund="NO (Salvo catástrofe, urgencia médica o avería grave)",
            budget_action="Ajustar Presupuesto Base si es recurrente o crear Sinking Fund",
        )

        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.NEEDS_DEFICIT,
                severity=GuidelineSeverity.ALERT,
                title=f"Déficit en Necesidades Básicas (+{excess_nec:,.2f} € sobre el 50%)",
                summary_headline=(
                    f"Tus gastos fijos indispensables han alcanzado {real_needs:,.2f} €, superando en {excess_nec:,.2f} € "
                    f"la cota del 50% ({target_needs:,.2f} €). ¿Debería salir del Fondo de Emergencia? En el 95% de los casos, NO."
                ),
                delta_amount=round(excess_nec, 2),
                delta_percentage=round(delta_pct_nec, 2),
                compensation_hierarchy=steps_nec,
                synoptic_row=syn_row2,
                emergency_fund_rule="NO en el 95% de los casos. Las facturas habituales o picos de consumo diario jamás deben mermar el colchón de seguridad.",
                key_recommendation="Aplica la jerarquía de compensación: canibaliza primero del bloque de Deseos y absorbe el resto reduciendo el ahorro mensual.",
            )
        )
        synoptic_table.append(syn_row2)

    # 3. CASO 3: EXCESO EN DESEOS (real_wants > target_wants)
    if real_income > 0 and real_wants > target_wants:
        excess_wants = real_wants - target_wants
        delta_pct_wants = (excess_wants / real_income * 100.0)

        steps_wants: List[CompensationStep] = [
            CompensationStep(
                priority=1,
                source_block="Ahorro e Inversión (20%) de este mes",
                amount=round(excess_wants, 2),
                action_text=f"Sale directa e inevitablemente de tu ahorro mensual: la tasa de ahorro baja en {delta_pct_wants:.1f} puntos porcentuales.",
                can_touch_emergency_fund=False,
            )
        ]

        strat_wants_a = GuidelineActionStrategy(
            name="Opción A: Ajuste Compensatorio el Mes Siguiente (Recomendada)",
            badge="Disciplina",
            allocation_amount=round(excess_wants, 2),
            description="Autocastigo financiero constructivo para restituir el patrimonio.",
            breakdown_items=[
                f"Reducir tu presupuesto de Deseos del próximo mes en {excess_wants:,.2f} €.",
                f"Transferir esos {excess_wants:,.2f} € directamente a tu cuenta de inversión para devolver el capital que restaste a tu futuro.",
            ],
        )

        strat_wants_b = GuidelineActionStrategy(
            name="Opción B: Aceptar la Bajada Puntual y Auditar la Desviación",
            badge="Auditoría",
            allocation_amount=round(excess_wants, 2),
            description="Aceptar la menor tasa de ahorro de este mes manteniendo estricta vigilancia sobre el Lifestyle Creep.",
            breakdown_items=[
                "Asumir que este mes el ahorro fue menor y vigilar que no se repita en meses sucesivos.",
                "Frenar compras impulsivas o cenas recurrentes para no acostumbrar al cerebro a un nivel de gasto superior.",
            ],
        )

        syn_row3 = SynopticTableRow(
            scenario_name="Exceso en Deseos (Caprichos)",
            funding_source="Exclusivamente del Ahorro del mes (20%)",
            touch_emergency_fund="NUNCA",
            budget_action="Celda en rojo. Opción de compensar recortando Deseos el mes siguiente",
        )

        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.WANTS_DEFICIT,
                severity=GuidelineSeverity.WARNING,
                title=f"Exceso en Deseos y Estilo de Vida (+{excess_wants:,.2f} € sobre el 30%)",
                summary_headline=(
                    f"Has gastado {real_wants:,.2f} € en Deseos (meta: {target_wants:,.2f} €), con un exceso de {excess_wants:,.2f} €. "
                    f"Este sobrecoste se deduce íntegra e inmediatamente de tu Ahorro de este mes."
                ),
                delta_amount=round(excess_wants, 2),
                delta_percentage=round(delta_pct_wants, 2),
                compensation_hierarchy=steps_wants,
                strategies=[strat_wants_a, strat_wants_b],
                synoptic_row=syn_row3,
                emergency_fund_rule="JAMÁS. Tocar el Fondo de Emergencia por caprichos u ocio es una falta contable grave que dinamita tu futuro.",
                key_recommendation="Aplica un ajuste compensatorio recortando Deseos en el mes siguiente para transferir ese importe a tu cartera de inversión.",
            )
        )
        synoptic_table.append(syn_row3)

    # 4. CASO 4: CAÍDA TEMPORAL DE INGRESOS (real_income < budget_income * 0.95)
    if budget_income > 0 and real_income < (budget_income * 0.95):
        drop = budget_income - real_income
        drop_pct = (drop / budget_income * 100.0)

        syn_row4 = SynopticTableRow(
            scenario_name="Caída de Ingresos Netos",
            funding_source="Congelación de Deseos y Pausa en Inversión",
            touch_emergency_fund="Solo si los ingresos no alcanzan para cubrir Necesidades mínimas",
            budget_action="Activar protocolo de contención de gastos no esenciales",
        )

        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.INCOME_SHORTFALL,
                severity=GuidelineSeverity.ALERT,
                title=f"Caída de Ingresos Netos (-{drop:,.2f} € / -{drop_pct:.1f}% vs Presupuesto)",
                summary_headline=(
                    f"Tus ingresos de este mes ({real_income:,.2f} €) han sido inferiores a los presupuestados ({budget_income:,.2f} €). "
                    f"Se activa el Protocolo de Contención de Gastos."
                ),
                delta_amount=round(drop, 2),
                delta_percentage=round(drop_pct, 2),
                synoptic_row=syn_row4,
                emergency_fund_rule="CONDICIONAL: Únicamente si tus ingresos netos no alcanzan para pagar el 100% de tus Necesidades Básicas mínimas.",
                key_recommendation="Congela gastos en Deseos que no tengan penalización contractual y pausa las aportaciones a inversión mientras duren los ingresos reducidos.",
            )
        )
        synoptic_table.append(syn_row4)

    # 5. CASO 5: INGRESO EXTRAORDINARIO / BONUS / PAGA EXTRA (real_income > budget_income * 1.05)
    if budget_income > 0 and real_income > (budget_income * 1.05):
        extra = real_income - budget_income
        extra_pct = (extra / budget_income * 100.0)

        strat_bonus_ef = GuidelineActionStrategy(
            name="Inyección a Seguridad Patrimonial (Fondo de Emergencia)",
            badge="Prioridad 1",
            allocation_amount=round(extra, 2),
            description="Si tu Fondo de Emergencia no alcanza la meta de cobertura, el 100% del ingreso extraordinario debe ir al fondo.",
            breakdown_items=[
                f"Aportación recomendada al Fondo de Emergencia: {min(extra, ef_gap):,.2f} €.",
                f"Remanente a inversión a largo plazo: {max(0.0, extra - ef_gap):,.2f} €.",
            ],
        )

        strat_bonus_rule = GuidelineActionStrategy(
            name="Regla de Bonus (80% Inversión / 20% Disfrute)",
            badge="Si Fondo Completo",
            allocation_amount=round(extra, 2),
            description="Distribución equilibrada una vez cubierto el colchón de seguridad.",
            breakdown_items=[
                f"80% ({extra * 0.8:,.2f} €) a Inversión o Amortización de Deuda: Aumentas el patrimonio a largo plazo.",
                f"20% ({extra * 0.2:,.2f} €) a Deseos / Experiencias: Disfrute libre de culpa sin descapitalización.",
            ],
        )

        syn_row5 = SynopticTableRow(
            scenario_name="Ingreso Extraordinario (Bonus / Paga Extra)",
            funding_source="100% a Fondo de Emergencia (si falta) o Inversión (80%) + Deseos (20%)",
            touch_emergency_fund="NO se retira. Se aporta dinero al fondo si está en construcción",
            budget_action="Asignar según regla 80/20 de bonus",
        )

        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.EXTRAORDINARY_INCOME,
                severity=GuidelineSeverity.INFO,
                title=f"Ingreso Extraordinario (+{extra:,.2f} € / +{extra_pct:.1f}% vs Presupuesto)",
                summary_headline=(
                    f"Has obtenido un ingreso de {real_income:,.2f} €, superior en {extra:,.2f} € a tu base presupuestada ({budget_income:,.2f} €). "
                    f"Aprovecha esta entrada extraordinaria con estrategia patrimonial."
                ),
                delta_amount=round(extra, 2),
                delta_percentage=round(extra_pct, 2),
                strategies=[strat_bonus_ef, strat_bonus_rule],
                synoptic_row=syn_row5,
                emergency_fund_rule="Se inyecta capital al fondo si la meta de cobertura no está completada.",
                key_recommendation="Si tu Fondo de Emergencia no está lleno, aporta el 100% del extra. Si ya está completo, aplica la regla 80/20 a inversión y disfrute.",
            )
        )
        synoptic_table.append(syn_row5)

    # 6. CASO 6: DINERO SIN ASIGNAR ELEVADO (> 5% de los ingresos)
    if real_income > 0 and unassigned_amount > (real_income * 0.05):
        unassigned_pct = (unassigned_amount / real_income * 100.0)

        syn_row6 = SynopticTableRow(
            scenario_name="Dinero Sin Asignar",
            funding_source="Cuenta corriente hacia Ahorro / Inversión",
            touch_emergency_fund="Canalizar al fondo si falta cobertura",
            budget_action="Asignar a subcategoría específica de ahorro o inversión antes de fin de mes",
        )

        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.HIGH_UNASSIGNED,
                severity=GuidelineSeverity.WARNING,
                title=f"Dinero Sin Asignar Elevado ({unassigned_amount:,.2f} € / {unassigned_pct:.1f}%)",
                summary_headline=(
                    f"Tienes {unassigned_amount:,.2f} € sin categorizar en el mes. Riesgo de liquidez invisible: "
                    f"el dinero no etiquetado en cuenta corriente suele disolverse en microgastos no registrados."
                ),
                delta_amount=round(unassigned_amount, 2),
                delta_percentage=round(unassigned_pct, 2),
                synoptic_row=syn_row6,
                emergency_fund_rule="Canalizar hacia el fondo de emergencia o hacia inversión antes de que termine el mes.",
                key_recommendation="Etiqueta y transfiere este capital para que cada euro tenga un propósito concreto (Ahorro, Inversión o provisión).",
            )
        )
        synoptic_table.append(syn_row6)

    # 7. CASO ÓPTIMO (Si no hay desviaciones adversas)
    if not guidelines:
        syn_row_opt = SynopticTableRow(
            scenario_name="Mes Equilibrado (50/30/20)",
            funding_source="Presupuesto ejecutado según diseño",
            touch_emergency_fund="NO",
            budget_action="Mantener la disciplina y continuar aportaciones periódicas",
        )
        guidelines.append(
            MonthlyGuidelineItem(
                scenario_type=MonthlyScenarioType.OPTIMAL,
                severity=GuidelineSeverity.INFO,
                title="Gestión Presupuestaria Óptima",
                summary_headline="Tu distribución mensual cumple perfectamente los límites del modelo 50/30/20.",
                delta_amount=0.0,
                delta_percentage=0.0,
                synoptic_row=syn_row_opt,
                emergency_fund_rule="NO se toca.",
                key_recommendation="Mantén la disciplina financiera y asegura tus transferencias automáticas a inversión y ahorro.",
            )
        )
        synoptic_table.append(syn_row_opt)

    # Determinar severidad y estado global
    has_alert = any(g.severity == GuidelineSeverity.ALERT for g in guidelines)
    has_warning = any(g.severity == GuidelineSeverity.WARNING for g in guidelines)

    if has_alert:
        overall_status = "Desviación Presupuestaria Relevante"
        status_severity = GuidelineSeverity.ALERT
    elif has_warning:
        overall_status = "Atención Requerida"
        status_severity = GuidelineSeverity.WARNING
    else:
        overall_status = "Cumplimiento Presupuestario Óptimo"
        status_severity = GuidelineSeverity.INFO

    return MonthlyGuidelineReport(
        month_key=month_key,
        month_name=month_name,
        overall_status=overall_status,
        status_severity=status_severity,
        guidelines=guidelines,
        synoptic_table=synoptic_table,
        real_income=round(real_income, 2),
        real_needs=round(real_needs, 2),
        real_wants=round(real_wants, 2),
        real_savings=round(real_savings, 2),
        unassigned_amount=round(unassigned_amount, 2),
        savings_rate=round(savings_rate, 2),
        emergency_fund_coverage_months=round(cov_months, 1),
        emergency_fund_target_months=round(tgt_months, 1),
        is_emergency_fund_completed=is_ef_completed,
    )


def evaluate_annual_guidelines(
    annual_metrics: Dict[str, Any],
    safety_status: Optional[Dict[str, Any]] = None,
) -> AnnualGuidelineReport:
    """
    Evalúa el estado financiero consolidado anual y genera diagnósticos estructurales
    sobre rigidez de costes, tasa de ahorro, lifestyle creep y exceso de liquidez ociosa.
    """
    ingresos = float(annual_metrics.get("ingresos_anual_real", 0.0))
    nec_anual = float(annual_metrics.get("nec_anual_real", 0.0))
    des_anual = float(annual_metrics.get("des_anual_real", 0.0))
    aho_anual = float(annual_metrics.get("aho_anual_real", 0.0))

    pct_nec = float(annual_metrics.get("pct_nec_real", 0.0))
    pct_des = float(annual_metrics.get("pct_des_real", 0.0))
    pct_aho = float(annual_metrics.get("pct_aho_real", 0.0))
    tasa_ahorro_media = (aho_anual / ingresos * 100.0) if ingresos > 0 else 0.0
    ahorro_acumulado_total = float(annual_metrics.get("ahorro_acumulado_total", 0.0))

    guidelines: List[AnnualGuidelineItem] = []

    # 1. Tasa de Ahorro Anual Deficitaria (< 20%)
    if ingresos > 0 and tasa_ahorro_media < 20.0:
        gap_pct = 20.0 - tasa_ahorro_media
        gap_euros = (gap_pct / 100.0) * ingresos
        guidelines.append(
            AnnualGuidelineItem(
                scenario_type=AnnualScenarioType.ANNUAL_SAVINGS_DEFICIT,
                severity=GuidelineSeverity.WARNING,
                title=f"Tasa de Ahorro Anual Deficitaria ({tasa_ahorro_media:.1f}% vs 20.0% objetivo)",
                description=(
                    f"Tu ahorro consolidado este año fue de {aho_anual:,.2f} €, lo que representa una tasa media del {tasa_ahorro_media:.1f}%. "
                    f"Has quedado a {gap_pct:.1f} puntos porcentuales ({gap_euros:,.2f} €) del objetivo base del 20%."
                ),
                metric_value_text=f"{tasa_ahorro_media:.1f}%",
                action_plan=(
                    "Auditoría de fuga: Revisa la matriz mensual para identificar si la desviación provino de meses específicos con "
                    "picos de gastos fijos (seguros, impuestos, revisiones) o de un sobregasto continuo en Deseos. Para el próximo ejercicio, "
                    "constituye un Fondo de Amortización (Sinking Fund) mensualizado dentro del 50% para que los gastos anuales no mermen tu tasa de ahorro."
                ),
            )
        )

    # 2. Lifestyle Creep (Deseos Anuales > 30%)
    if ingresos > 0 and pct_des > 30.0:
        excess_des_pct = pct_des - 30.0
        excess_des_euros = (excess_des_pct / 100.0) * ingresos
        guidelines.append(
            AnnualGuidelineItem(
                scenario_type=AnnualScenarioType.LIFESTYLE_CREEP,
                severity=GuidelineSeverity.WARNING,
                title=f"Inflación del Estilo de Vida en Deseos ({pct_des:.1f}% vs 30.0%)",
                description=(
                    f"El gasto en ocio, viajes y estilo de vida alcanzó {des_anual:,.2f} € ({pct_des:.1f}% del total anual), "
                    f"superando el umbral prudencial en {excess_des_euros:,.2f} €."
                ),
                metric_value_text=f"{pct_des:.1f}%",
                action_plan=(
                    "Desindexación del ocio: Establece techos mensuales improrrogables para ocio y caprichos. Desvincula los incrementos salariales "
                    "del aumento automático del nivel de vida y automatiza el 'págate a ti primero' a principios de mes."
                ),
            )
        )

    # 3. Rigidez de Gastos Fijos (Necesidades Anuales > 50%)
    if ingresos > 0 and pct_nec > 50.0:
        excess_nec_pct = pct_nec - 50.0
        excess_nec_euros = (excess_nec_pct / 100.0) * ingresos
        guidelines.append(
            AnnualGuidelineItem(
                scenario_type=AnnualScenarioType.FIXED_COST_RIGIDITY,
                severity=GuidelineSeverity.ALERT,
                title=f"Rigidez Estructural de Necesidades Básicas ({pct_nec:.1f}% vs 50.0%)",
                description=(
                    f"Tus costes fijos indispensables ascendieron a {nec_anual:,.2f} € ({pct_nec:.1f}% de tus ingresos), "
                    f"excediendo en {excess_nec_euros:,.2f} € el marco 50/30/20."
                ),
                metric_value_text=f"{pct_nec:.1f}%",
                action_plan=(
                    "Revisión de estructura de vida: Tu nivel de gasto indispensable supera la capacidad de tu presupuesto. Antes de aumentar "
                    "el riesgo en bolsa, renegocia contratos de suministros, telecomunicaciones, seguros e hipoteca/alquiler para devolver "
                    "holgura a tu economía doméstica."
                ),
            )
        )

    # 4. Exceso de Liquidez Ociosa / Coste de Oportunidad
    necesidad_mensual_media = (nec_anual / 12.0) if nec_anual > 0 else 0.0
    if necesidad_mensual_media > 0 and ahorro_acumulado_total > (necesidad_mensual_media * 12.0):
        meses_cubiertos = ahorro_acumulado_total / necesidad_mensual_media
        guidelines.append(
            AnnualGuidelineItem(
                scenario_type=AnnualScenarioType.IDLE_CASH,
                severity=GuidelineSeverity.INFO,
                title=f"Exceso de Liquidez Ociosa ({ahorro_acumulado_total:,.2f} € acumulados / {meses_cubiertos:.1f} meses)",
                description=(
                    f"Tu ahorro acumulado total asciende a {ahorro_acumulado_total:,.2f} €, lo que equivale a {meses_cubiertos:.1f} meses "
                    f"de tus necesidades básicas medias ({necesidad_mensual_media:,.2f} €/mes). Supera con holgura el colchón de seguridad estándar de 6-12 meses."
                ),
                metric_value_text=f"{meses_cubiertos:.1f} meses",
                action_plan=(
                    "Mitigación de coste de oportunidad frente a inflación: Mantener liquidez excesiva en cuenta corriente pierde poder adquisitivo. "
                    "Planifica un calendario de aportaciones periódicas promediadas (DCA) a fondos indexados globales para poner a trabajar el capital excedentario."
                ),
            )
        )

    # 5. Estado Equilibrado
    if not guidelines:
        guidelines.append(
            AnnualGuidelineItem(
                scenario_type=AnnualScenarioType.ANNUAL_BALANCED,
                severity=GuidelineSeverity.INFO,
                title="Salud Financiera Consolidada Óptima",
                description="Tu consolidado anual cumple con solvencia la distribución 50/30/20 y una tasa de ahorro saludable.",
                metric_value_text=f"{tasa_ahorro_media:.1f}%",
                action_plan="Continúa con tu disciplina patrimonial y revisa tus objetivos de inversión a largo plazo.",
            )
        )

    has_alert = any(g.severity == GuidelineSeverity.ALERT for g in guidelines)
    has_warning = any(g.severity == GuidelineSeverity.WARNING for g in guidelines)

    if has_alert:
        overall_health = "Rigidez Financiera Estructural"
        status_severity = GuidelineSeverity.ALERT
        summary_text = "Se detecta rigidez excesiva en gastos fijos. Se recomienda auditar contratos y renegociar costes estructurales."
    elif has_warning:
        overall_health = "Desviaciones Anuales Moderadas"
        status_severity = GuidelineSeverity.WARNING
        summary_text = "Se observan desviaciones en la tasa de ahorro o estilo de vida. Conviene recalibrar presupuestos y aplicar Sinking Funds."
    else:
        overall_health = "Excelente Salud Financiera Anual"
        status_severity = GuidelineSeverity.INFO
        summary_text = "Tus finanzas anuales muestran equilibrio, tasa de ahorro adecuada y control riguroso de gastos."

    return AnnualGuidelineReport(
        overall_health=overall_health,
        status_severity=status_severity,
        average_savings_rate=round(tasa_ahorro_media, 2),
        guidelines=guidelines,
        summary_text=summary_text,
    )
