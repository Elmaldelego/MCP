import logging
from datetime import datetime

from models import (
    EnvironmentalContextValidation, EnvironmentalThreat,
    EnvironmentalAnalysisResult
)

logger = logging.getLogger("vigia.environmental_monitoring_service")

# ── Risk Matrix (Environmental Monitoring) ──────────────────────────────────
# Severity (1-4) x Occurrence (1-3)
# Total Risk = Severity * Occurrence (1-12)
# Same MRO matrix used by Food Defense

def get_risk_level(score: int) -> str:
    if score >= 9: return "High"
    if score >= 4: return "Medium"
    return "Low"

# ── Context Validation Logic ──────────────────────────────────────────────

VALIDATION_CRITERIA = [
    {"id": "process_areas", "label": "Áreas o zonas de proceso evaluadas", "weight": 20, "critical": True,
     "signals": ["áreas", "zonas", "proceso", "ambiente", "instalaciones", "área de", "salas", "cuartos", "areas", "zona"]},
    {"id": "microbiological_hazards", "label": "Riesgos microbiológicos identificados (patógenos, coliformes, etc.)", "weight": 25, "critical": True,
     "signals": ["microbiológico", "patógenos", "coliformes", "bacterias", "hongos", "levaduras", "listeria", "salmonella", "e. coli", "microbiological", "pathogens"]},
    {"id": "sanitation_measures", "label": "Medidas de saneamiento, limpieza y desinfección", "weight": 20, "critical": True,
     "signals": ["limpieza", "saneamiento", "desinfección", "sanitización", "higiene", "sanitizacion", "cleaning", "sanitation"]},
    {"id": "monitoring_controls", "label": "Controles actuales de monitoreo ambiental", "weight": 20, "critical": False,
     "signals": ["monitoreo", "monitoreo ambiental", "muestreo", "verificación", "control", "criterios", "monitoring", "sampling"]},
    {"id": "area_classification", "label": "Categorización o clasificación de áreas", "weight": 15, "critical": False,
     "signals": ["categorización", "clasificación", "categoria", "tipo de área", "área crítica", "área no crítica", "categorizacion", "clasificacion"]},
]

def validate_context(available_context: str) -> EnvironmentalContextValidation:
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
                "why": f"No se encontraron señales de: {criterion['label']}",
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
        xlsx_stamp = "Análisis verificado — contexto completo"
    elif score >= 40 and not critical_missing:
        gate = "PARTIAL"
        can_proceed = True
        xlsx_stamp = f"Análisis preliminar — score {score}/100"
        user_message = "El contexto es parcial. Faltan algunos elementos no críticos. Desea continuar?"
    else:
        gate = "BLOCKED"
        can_proceed = False
        user_message = "Análisis bloqueado. Falta información crítica o el score es demasiado bajo."

    return EnvironmentalContextValidation(
        gate=gate,
        score=score,
        present=present,
        missing=missing,
        critical_missing=critical_missing,
        user_message=user_message,
        xlsx_stamp=xlsx_stamp,
        can_proceed=can_proceed
    )

# ── Threat Patterns ──────────────────────────────────────────────────────

ENV_MONITORING_PATTERNS = [
    {
        "area": "Recepción y almacenamiento de materias primas",
        "category": "Alta criticidad",
        "keywords": ["recepción", "almacenamiento", "materias primas", "bodega", "almacén", "receiving", "storage", "warehouse"],
        "micro_risks": "Coliformes totales, Escherichia coli, Salmonella spp., mohos y levaduras",
        "activators": "Aire ambiental del muelle, personal de descarga, pallets de madera, condensación en cámara frigorífica",
        "sanitation": "Limpieza y sanitización diaria de pisos y paredes, rotación FIFO, control de temperatura y humedad",
        "severity": 4,
        "occurrence": 2,
        "controls": "Filtración de aire en cámara, muestreo microbiológico semanal de superficies",
        "frequency": "Mensual"
    },
    {
        "area": "Área de procesamiento / producción",
        "category": "Alta criticidad",
        "keywords": ["procesamiento", "producción", "proceso", "manufactura", "elaboración", "processing", "production", "manufacturing"],
        "micro_risks": "Listeria monocytogenes, Salmonella spp., Staphylococcus aureus, Coliformes",
        "activators": "Personal en contacto con producto, aerosoles de limpieza, acumulación de agua en pisos, equipos mal sanitizados, condensación en tuberías",
        "sanitation": "Sanitización de equipos cada cambio de turno, lavado de manos obligatorio, drenajes con sello hidráulico",
        "severity": 4,
        "occurrence": 2,
        "controls": "Monitoreo de Listeria spp. en zonas húmedas, control de temperatura ambiente, muestreo de superficies",
        "frequency": "Semanal"
    },
    {
        "area": "Área de envasado / empaque",
        "category": "Alta criticidad",
        "keywords": ["envasado", "empaque", "packaging", "envase", "embalaje"],
        "micro_risks": "Mohos, levaduras, Enterobacterias, Coliformes",
        "activators": "Material de empaque contaminado, aire ambiental, personal de empaque, humedad relativa elevada",
        "sanitation": "Limpieza de líneas de empaque cada turno, sanitización de selladoras, control de plagas",
        "severity": 3,
        "occurrence": 2,
        "controls": "Monitoreo de aire ambiental (sedimentación en placa), verificación de sanitización de empaque",
        "frequency": "Quincenal"
    },
    {
        "area": "Cámaras de refrigeración / congelación",
        "category": "Media criticidad",
        "keywords": ["cámara", "refrigeración", "congelación", "frigorífico", "refrigerador", "cooler", "freezer", "cold"],
        "micro_risks": "Listeria monocytogenes, Pseudomonas spp., mohos psicrófilos",
        "activators": "Condensación en evaporadores, acumulación de agua en pisos, falta de limpieza en cortinas sanitarias, ingreso de materia prima contaminada",
        "sanitation": "Limpieza profunda programada, control de escarcha, sanitización de cortinas plásticas, drenajes limpios",
        "severity": 3,
        "occurrence": 1,
        "controls": "Monitoreo de temperatura continua, muestreo de superficies en contacto, inspección visual semanal",
        "frequency": "Mensual"
    },
    {
        "area": "Área de servicios e instalaciones",
        "category": "Media criticidad",
        "keywords": ["servicios", "instalaciones", "cisterna", "agua", "drenaje", "mantenimiento", "utility", "water", "drain"],
        "micro_risks": "Pseudomonas aeruginosa, Coliformes totales, Legionella, mohos ambientales",
        "activators": "Agua de proceso no tratada, cisternas sin sanitizar, drenajes obsoletos, sistema de ventilación sin mantenimiento, condensación en tuberías",
        "sanitation": "Sanitización de cisternas semestral, mantenimiento de trampas de grasa, limpieza de ductos de ventilación",
        "severity": 2,
        "occurrence": 2,
        "controls": "Análisis fisicoquímico y microbiológico de agua potable, inspección de drenajes, mantenimiento preventivo",
        "frequency": "Trimestral"
    },
    {
        "area": "Área de personal / vestidores",
        "category": "Baja criticidad",
        "keywords": ["vestidores", "baños", "sanitarios", "personal", "locker", "bathroom", "restroom", "dressing"],
        "micro_risks": "Staphylococcus aureus, Coliformes fecales, hongos en duchas",
        "activators": "Personal como vehículo de contaminación cruzada, malas prácticas higiénicas, falta de separación de áreas sucias/limpias",
        "sanitation": "Limpieza y desinfección diaria de vestidores, lavamanos con jabón antibacterial, separación de áreas sucias y limpias",
        "severity": 2,
        "occurrence": 1,
        "controls": "Verificación de prácticas de lavado de manos, supervisión de limpieza de vestidores",
        "frequency": "Mensual"
    }
]

def analyze_environmental_risks(
    context: str,
    gate_result: dict,
    company_name: str,
    process_area: str
) -> EnvironmentalAnalysisResult:
    context_lower = context.lower()
    threats = []
    threat_id_counter = 1

    for pattern in ENV_MONITORING_PATTERNS:
        if any(kw in context_lower for kw in pattern["keywords"]):
            severity = pattern["severity"]
            occurrence = pattern["occurrence"]
            score = severity * occurrence

            res_sev = max(1, severity - 1)
            res_occ = max(1, occurrence - 1)
            res_score = res_sev * res_occ

            threats.append(EnvironmentalThreat(
                id=f"EM{threat_id_counter:03d}",
                area=pattern["area"],
                area_category=pattern["category"],
                microbiological_risk=pattern["micro_risks"],
                risk_activators=pattern["activators"],
                sanitation_abilities=pattern["sanitation"],
                severity=severity,
                occurrence=occurrence,
                risk_score=score,
                risk_level=get_risk_level(score),
                special_controls=pattern["controls"],
                verification_frequency=pattern["frequency"],
                residual_severity=res_sev,
                residual_occurrence=res_occ,
                residual_risk_score=res_score,
                residual_risk_level=get_risk_level(res_score)
            ))
            threat_id_counter += 1

    high_priority_count = sum(1 for t in threats if t.risk_score >= 9)

    return EnvironmentalAnalysisResult(
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
