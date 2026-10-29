# Especificaciones del Proyecto (Spec-Driven Development)

Índice y estado de las especificaciones del sistema:

| Spec | Nombre | Estado | Descripción |
| :--- | :--- | :--- | :--- |
| **000-map** | [Mapa de Arquitectura](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/000-architecture-map/design-report.md) | **Aprobado** | Descomposición global, contratos técnicos y hoja de ruta secuencial. |
| **000** | [Cimientos y Safety Guard](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/000-cimientos-safety-guard/spec.md) | **Completada** | Suite `pytest` (23 tests), servicios desacoplados en backend y entidad dinámica `EmergencyFund`. |
| **001** | [Radar Macro y Noticias](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/001-radar-macro-noticias/spec.md) | **Completada** | Contexto macroeconómico, fuentes de noticias y filtro de impacto sin sensacionalismo. |
| **002** | [Screener y Oportunidades](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/002-screener-oportunidades/spec.md) | **Completada** | Filtrado cuantitativo de acciones y ETFs por múltiplos contables y volumen (Opción B: Universos Modulares). |
| **003** | [Análisis Fundamental (Deep Dive)](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/003-analisis-fundamental/spec.md) | **Completada** | Diagnóstico contable individual, Piotroski F-Score (0-9), FCF, Watchlist y síntesis agéntica Quality Value con Gemini (3.1 Flash / 2.5 Pro). |
| **004** | [Copiloto Patrimonial](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/004-copiloto-patrimonial/spec.md) | **Completada** | Asistente asesor con Function Calling bajo demanda, doble tesis, persistencia local en SQLite y salvaguarda de riesgo. |
| **005** | [Orquestación LangGraph](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/005-orquestacion-langgraph/spec.md) | **Completada** | Comité Asesor de Inversión Multiagente con StateGraph de LangGraph, arquitectura modular (agents, components, domain, external_components), veto constitucional vinculante (Principio 9) y doble tesis obligatoria (Principio 12). |
| **006** | [Gestión de Transacciones](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/006-gestion-transacciones/spec.md) | **Completada** | Visor de historial mensual, eliminación segura con confirmación y reversión automática del saldo del Fondo de Emergencia. |
| **007** | [Sistema de Logs Rotativos](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/007-sistema-logs-rotativos/spec.md) | **Completada** | Logs independientes (backend.log y frontend.log), rotación por tamaño (5 MB, 3 backups), middleware de latencia, nivel INFO por defecto y PrivacyFilter. |
| **008** | [Pautas de Gestión Determinista](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/008-pautas-gestion-determinista/spec.md) | **Aprobada** | Pautas de actuación, jerarquías de compensación y diagnósticos deterministas con cifras reales bajo 50/30/20 para meses y resumen anual. |


---

### Archivo
- [archive/001-analisis-mercado/spec.md](file:///c:/Users/Raul_515/Desktop/ProyectosAntigravity/GestorFinanzas/specs/archive/001-analisis-mercado/spec.md): Borrador inicial de análisis de mercado, archivado para ser reescrito con alcance ampliado en Spec 003.
