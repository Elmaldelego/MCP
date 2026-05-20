import logging
from datetime import datetime

from models import AllergenContextValidation, AllergenThreat, AllergenAnalysisResult

logger = logging.getLogger("vigia.allergen_management_service")

# ── Matrix de Riesgo (Food Fraud) ──────────────────────────────────────────
# Severidad (I-IV) x Ocurrencia (A-E)
_RISK_MATRIX = {
    "I":  {"A": 1,  "B": 2,  "C": 6,  "D": 8,  "E": 12},
    "II": {"A": 3,  "B": 4,  "C": 7,  "D": 11, "E": 15},
    "III":{"A": 5,  "B": 9,  "C": 10, "D": 14, "E": 16},
    "IV": {"A": 13, "B": 17, "C": 18, "D": 19, "E": 20},
}

_SEVERITY_LABELS = {
    "I": "Catastrophic",
    "II": "Critical",
    "III": "Moderate",
    "IV": "Negligible",
}

_OCCURRENCE_LABELS = {
    "A": "Frequent",
    "B": "Likely",
    "C": "Occasional",
    "D": "Seldom",
    "E": "Unlikely",
}

def get_risk_level(score: int) -> str:
    if 1 <= score <= 4: return "Extremely High"
    if 5 <= score <= 8: return "High"
    if 9 <= score <= 14: return "Medium"
    return "Low"

# ── Context Validation ────────────────────────────────────────────────────

VALIDATION_CRITERIA = [
    {"id": "allergen_areas", "label": "Areas o procesos donde se manejan alergenos", "weight": 20, "critical": True,
     "signals": ["areas", "proceso", "almacen", "produccion", "envasado", "cocina", "recepcion", "linea"]},
    {"id": "allergen_types", "label": "Tipos de alergenos involucrados (leche, soya, huevo, etc.)", "weight": 25, "critical": True,
     "signals": ["alergeno", "leche", "soya", "huevo", "almendra", "nuez", "cacahuate", "gluten", "lactosa", "amarillo", "trigo", "soja", "allergen"]},
    {"id": "risk_description", "label": "Descripcion de riesgos de contacto cruzado", "weight": 20, "critical": True,
     "signals": ["riesgo", "contacto cruzado", "contaminacion", "derrames", "exposicion", "cruzada", "cruce"]},
    {"id": "current_controls", "label": "Controles actuales (PPRs, limpieza, etiquetado)", "weight": 20, "critical": False,
     "signals": ["controles", "limpieza", "etiquetado", "procedimientos", "ppr", "programa", "plan de manejo"]},
    {"id": "verification_methods", "label": "Metodos y frecuencia de verificacion", "weight": 15, "critical": False,
     "signals": ["verificacion", "frecuencia", "monitoreo", "inspeccion", "registros", "autoinspection"]},
]

def validate_context(available_context: str) -> AllergenContextValidation:
    context_lower = available_context.lower()
    score = 0
    present = []
    missing = []
    critical_missing = False

    for criterion in VALIDATION_CRITERIA:
        is_present = any(signal in context_lower for signal in criterion["signals"])
        if is_present:
            score += criterion["weight"]
            present.append(criterion["id"])
        else:
            missing.append({
                "id": criterion["id"],
                "label": criterion["label"],
                "why": f"No se encontraron senales de: {criterion['label']}",
                "critical": criterion["critical"]
            })
            if criterion["critical"]:
                critical_missing = True

    gate = "BLOCKED"
    can_proceed = False
    user_message = ""
    xlsx_stamp = ""

    if score >= 75 and not critical_missing:
        gate = "OPEN"
        can_proceed = True
        xlsx_stamp = "Analisis verificado — contexto completo"
    elif score >= 40 and not critical_missing:
        gate = "PARTIAL"
        can_proceed = True
        xlsx_stamp = f"Analisis preliminar — score {score}/100"
        user_message = "El contexto es parcial. Faltan algunos elementos no criticos. Desea continuar?"
    else:
        gate = "BLOCKED"
        can_proceed = False
        user_message = "Analisis bloqueado. Falta informacion critica o el score es demasiado bajo."

    return AllergenContextValidation(
        gate=gate, score=score, present=present, missing=missing,
        critical_missing=critical_missing, user_message=user_message,
        xlsx_stamp=xlsx_stamp, can_proceed=can_proceed
    )

# ── Allergen Risk Patterns ────────────────────────────────────────────────

ALLERGEN_PATTERNS = [
    {
        "area": "Almacen de producto terminado",
        "keywords": ["almacen pt", "almacen", "producto terminado", "bodega", "rack", "estanteria"],
        "allergens": "Lactosa, Soya, Almendra, Colorante Amarillo 5, Gluten",
        "risk": "Derrames de leche por mal manejo de operadores que contaminan otros productos almacenados. Mal etiquetado. Desapego a la estructura definida de almacenaje. Pesado de alergenos. Mal armado de kits o batch para proceso.",
        "controls": "Plan de manejo de alergenos, procedimientos de limpieza por derrames, KIT para limpieza, diseno de practicas de almacenaje en RACKs (mismo alergeno encima o debajo).",
        "severity": "II",
        "occurrence": "B",
        "special": "NO. Los controles actuales demuestran consistencia.",
        "frequency": "Verificacion durante la operacion. Modo de accion de operadores. Registros. Auto inspecciones rutinarias."
    },
    {
        "area": "Recepcion de materias primas",
        "keywords": ["recepcion", "materias primas", "descarga", "proveedor", "ingreso de material"],
        "allergens": "Leche en polvo, Harina de trigo, Clara de huevo deshidratada, Leche entera, Crema de leche",
        "risk": "Ingreso de materias primas alergenicas sin identificacion clara. Riesgo de almacenamiento conjunto con no alergenicos. Proveedores sin declaracion de alergenos en etiquetas.",
        "controls": "Verificacion de etiquetado en recepcion. Checklist de materiales alergenicos. Zona de cuarentena para materiales no identificados.",
        "severity": "III",
        "occurrence": "C",
        "special": "SI. Reforzar verificacion de documentos de proveedores y etiquetado.",
        "frequency": "Cada recepcion. Muestreo aleatorio del 10% de los lotes recibidos."
    },
    {
        "area": "Area de produccion / proceso",
        "keywords": ["produccion", "proceso", "manufactura", "elaboracion", "mezclado", "coccion", "formado"],
        "allergens": "Leche liquida, Huevo entero, Harina de trigo, Soya texturizada, Suero de leche",
        "risk": "Contacto cruzado por aerosolizacion de alergenos en polvo. Limpieza ineficiente entre corridas de productos con diferente perfil alergenico. Re-trabajo de producto sin control de alergenos. Orden de produccion inadecuado.",
        "controls": "Programacion de produccion por sensibilidad alergenica (no alergenicos primero). Procedimientos de limpieza CIP intermedia. Pruebas de ATP y proteinas residuales. Utensilios codificados por color.",
        "severity": "I",
        "occurrence": "B",
        "special": "SI. Implementar verificacion con pruebas de ELISA o lateral flow post-limpieza.",
        "frequency": "Prueba de proteinas residuales despues de cada limpieza entre cambios de perfil alergenico."
    },
    {
        "area": "Area de envasado / empaque",
        "keywords": ["envasado", "empaque", "packaging", "linea de empaque", "sellado", "etiquetado"],
        "allergens": "Trazas de todos los alergenos de produccion",
        "risk": "Error de etiquetado (etiqueta incorrecta en producto equivocado). Contaminacion cruzada por aerosol en ambiente de envasado. Cambio de formato sin limpieza profunda de tolvas y conductos.",
        "controls": "Verificacion de etiquetas por codigo de barras. Procedimiento de cambio de formato con checklist. Aire comprimido filtrado. Diferencial de presion en sala de envasado.",
        "severity": "II",
        "occurrence": "B",
        "special": "SI. Implementar sistema de verificacion de etiquetas con scanner y doble chequeo.",
        "frequency": "Verificacion al inicio de cada corrida y cada cambio de SKU."
    },
    {
        "area": "Cocina / area de preparacion",
        "keywords": ["cocina", "preparacion", "coccion", "cocina caliente", "cocina fria", "kitchen"],
        "allergens": "Leche, Huevo, Trigo, Soya, Pescado, Cacahuate, Nuez, Almendra",
        "risk": "Uso de mismos utensilios para diferentes alergenos. Salpicaduras durante coccion. Almacenamiento de ingredientes sin tapa. Manipuladores sin conocimiento de alergenos. Contaminacion cruzada en planchas y freidoras.",
        "controls": "Utensilios y areas de preparacion separadas por alergeno. Freidoras designadas por tipo de alergeno. Capacitacion del personal. Etiquetado de contenedores en buffete.",
        "severity": "I",
        "occurrence": "C",
        "special": "SI. Implementar programa de capacitacion en alergenos para todo el personal de cocina.",
        "frequency": "Verificacion visual diaria. Auditoria semanal de buenas practicas."
    },
    {
        "area": "Limpieza de equipos (CIP / COP)",
        "keywords": ["limpieza", "cip", "cop", "sanitizacion", "lavado de equipos", "higiene"],
        "allergens": "Residuos de proteinas alergenicas en equipos",
        "risk": "Limpieza ineficiente que deja residuos de proteinas alergenicas. Diseno de equipo con espacios muertos. Tiempos de limpieza insuficientes. Concentracion de detergente inadecuada. Agua de enjuague contaminada.",
        "controls": "Validacion de limpieza con pruebas de proteinas. Parametros de CIP documentados (tiempo, temperatura, concentracion). Inspeccion visual post-limpieza.",
        "severity": "II",
        "occurrence": "C",
        "special": "SI. Establecer frecuencia de validacion de limpieza basada en nivel de riesgo del producto.",
        "frequency": "Prueba de proteinas residuales post-CIP en equipos de alto riesgo. Semanal en equipos de uso frecuente."
    },
    {
        "area": "Etiquetado y liberacion de producto",
        "keywords": ["etiquetado", "liberacion", "empaque final", "codigo de barras", "lote"],
        "allergens": "Declaracion de alergenos en empaque",
        "risk": "Etiqueta con declaracion de alergenos incorrecta o incompleta. Producto en empaque equivocado. Cambio de formulacion no reflejado en etiqueta. Lote sin trazabilidad alergenica.",
        "controls": "Sistema de gestion de etiquetas con control de versiones. Revision de arte por equipo de inocuidad. Prueba de alergenos en producto terminado para etiquetas Puede contener.",
        "severity": "I",
        "occurrence": "B",
        "special": "SI. Implementar revision de etiquetas por equipo multidisciplinario antes de impresion.",
        "frequency": "Cada cambio de etiqueta o formulacion. Auditoria trimestral de etiquetado."
    }
]

def analyze_allergen_risks(
    context: str,
    gate_result: dict,
    company_name: str,
    process_area: str
) -> AllergenAnalysisResult:
    context_lower = context.lower()
    threats = []
    threat_id_counter = 1

    for pattern in ALLERGEN_PATTERNS:
        if any(kw in context_lower for kw in pattern["keywords"]):
            severity = pattern["severity"]
            occurrence = pattern["occurrence"]
            score = _RISK_MATRIX[severity][occurrence]

            res_sev_int = max(1, list(_SEVERITY_LABELS.keys()).index(severity))
            res_occ_int = max(1, list(_OCCURRENCE_LABELS.keys()).index(occurrence))
            res_sev_key = list(_SEVERITY_LABELS.keys())[res_sev_int - 1]
            res_occ_key = list(_OCCURRENCE_LABELS.keys())[res_occ_int - 1]
            res_score = _RISK_MATRIX[res_sev_key][res_occ_key]

            threats.append(AllergenThreat(
                id=f"AL{threat_id_counter:03d}",
                area=pattern["area"],
                allergens_involved=pattern["allergens"],
                risk_description=pattern["risk"],
                current_controls=pattern["controls"],
                severity=severity,
                severity_label=_SEVERITY_LABELS[severity],
                occurrence=occurrence,
                occurrence_label=_OCCURRENCE_LABELS[occurrence],
                risk_score=score,
                risk_level=get_risk_level(score),
                special_controls=pattern["special"],
                verification_frequency=pattern["frequency"],
                residual_severity=res_sev_key,
                residual_occurrence=res_occ_key,
                residual_risk_score=res_score,
                residual_risk_level=get_risk_level(res_score)
            ))
            threat_id_counter += 1

    high_priority_count = sum(1 for t in threats if t.risk_score <= 8)

    return AllergenAnalysisResult(
        threats=threats,
        total_threats=len(threats),
        high_priority_count=high_priority_count,
        analysis_metadata={
            "company_name": company_name,
            "process_area": process_area,
            "gate": gate_result.get("gate"),
            "score": gate_result.get("score"),
            "generated_at": datetime.now().isoformat()
        }
    )