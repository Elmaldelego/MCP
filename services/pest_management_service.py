import logging
from datetime import datetime

from models import (
    PestContextValidation, PestThreat, PestAnalysisResult
)

logger = logging.getLogger("vigia.pest_management_service")

# ── Risk Matrix (Pest Management 5x5) ───────────────────────────────────────
# Severity (1-5) x Occurrence (1-5)
# Total Risk = Sev * Ocurr (1-25)

def get_pest_risk_level(score: int) -> str:
    if score >= 25: return "Extremo"
    if score >= 12: return "Critico"
    if score >= 6: return "Alto"
    if score >= 4: return "Moderado"
    if score >= 2: return "Bajo"
    return "Minimo"

# ── Context Validation Logic ──────────────────────────────────────────────

VALIDATION_CRITERIA = [
    {"id": "operational_areas", "label": "Descripcion de areas operativas de la planta", "weight": 20, "critical": True,
     "signals": ["areas", "zonas", "instalaciones", "planta", "operativas", "almacen", "produccion", "proceso", "areas"]},
    {"id": "pest_types", "label": "Identificacion de tipos de plagas (roedores, insectos, aves, etc.)", "weight": 25, "critical": True,
     "signals": ["plagas", "roedores", "insectos", "aves", "ratas", "ratones", "cucarachas", "moscas", "gorgojo", "tribolium", "palomas", "pest", "rodent", "insect"]},
    {"id": "pest_causes", "label": "Causas potenciales de presencia de plagas (diseno sanitario, aberturas, MP)", "weight": 20, "critical": True,
     "signals": ["causas", "diseno sanitario", "espacios muertos", "aberturas", "ingreso", "puertas", "registros", "drenajes", "conductos"]},
    {"id": "current_controls", "label": "Controles actuales y monitoreo (bioindicadores, estaciones, cebado)", "weight": 20, "critical": False,
     "signals": ["control", "monitoreo", "bioindicadores", "estaciones", "cebado", "trampas", "inspeccion", "fumigacion"]},
    {"id": "action_plans", "label": "Acciones correctivas y plan de accion planta/proveedor", "weight": 15, "critical": False,
     "signals": ["acciones", "correctivas", "plan", "planta", "proveedor", "medidas", "sellan", "reparar", "instalar"]},
]

def validate_context(available_context: str) -> PestContextValidation:
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

    return PestContextValidation(
        gate=gate,
        score=score,
        present=present,
        missing=missing,
        critical_missing=critical_missing,
        user_message=user_message,
        xlsx_stamp=xlsx_stamp,
        can_proceed=can_proceed
    )

# ── Pest Threat Patterns ──────────────────────────────────────────────────

PEST_PATTERNS = [
    {
        "area": "Almacen de materias primas",
        "keywords": ["almacen", "materias primas", "bodega", "almacenamiento", "warehouse", "storage"],
        "pest_risk": "Roedores: Rattus norvegicus, Mus musculus | Insectos: Tribolium confusum, Gorgojo de la harina",
        "causes": "Puertas que no sellan completamente al piso, registros de agua pluvial en mal estado cercanos a rampa de descarga, materiales entrantes contaminados con plagas",
        "strategic": "Contaminacion de producto con riesgo de patogenos. Los roedores actuan como vectores de bacterias que contaminan ambiente, procesos y productos.",
        "operational": "El personal deja abiertos los accesos y puertas del almacen. No se aplica inspeccion formal a materiales entrantes. No se documentan incidentes con plagas.",
        "severity": 4,
        "occurrence": 4,
        "threshold": "Interior de almacen: Ausente. Exterior: menor a 5 bioindicadores por mes",
        "plant_actions": "Sellar y reparar registros pluviales. Instalar guardapolvos en puertas. Integrar checklist de inspeccion de MP entrantes con criterios de aceptacion/rechazo por plagas.",
        "supplier_actions": "Incluir en contrato de proveedores clausulas de envio y entrega con enfasis en plagas. Inspecciones rutinarias aleatorias en recepcion de MP para supervisar especie y poblacion."
    },
    {
        "area": "Area de produccion / proceso",
        "keywords": ["produccion", "proceso", "manufactura", "elaboracion", "processing", "production", "manufacturing"],
        "pest_risk": "Insectos rastreros: Cucarachas (Periplaneta americana) | Insectos voladores: Moscas (Musca domestica) | Roedores",
        "causes": "Acumulacion de residuos de producto en equipos y pisos, espacios muertos detras de maquinaria, drenajes sin sello hidraulico, condensacion en tuberias",
        "strategic": "Contaminacion directa del producto en proceso con patogenos transportados por plagas. Riesgo de recall y dano a la marca.",
        "operational": "La limpieza de equipos no incluye espacios internos. Los drenajes no reciben mantenimiento frecuente. Hay areas de dificil acceso detras de equipos.",
        "severity": 5,
        "occurrence": 3,
        "threshold": "Ausente en areas de produccion. Maximo 1 insecto volador por turno en areas semicriticas.",
        "plant_actions": "Implementar programa de limpieza profunda de equipos y espacios muertos. Sellar drenajes con malla y sello hidraulico. Instalar estaciones de cebado en puntos estrategicos perimetrales.",
        "supplier_actions": "Solicitar al proveedor de control de plagas incrementar frecuencia de visitas en epocas de alta temperatura. Reforzar estaciones de monitoreo perimetral."
    },
    {
        "area": "Area de envasado / empaque",
        "keywords": ["envasado", "empaque", "packaging", "envase", "embalaje"],
        "pest_risk": "Insectos voladores: Moscas pequenas (Drosophila spp.) | Insectos rastreros | Roedores",
        "causes": "Material de empaque almacenado directamente en piso, cortinas plasticas danadas, falta de mantenimiento en sellos de puertas, residuos de producto en empaques",
        "strategic": "Contaminacion de producto terminado. Riesgo de quejas de clientes y devoluciones.",
        "operational": "El material de empaque se almacena en el piso por falta de estanterias. Las cortinas plasticas tienen orificios que permiten ingreso de insectos voladores.",
        "severity": 4,
        "occurrence": 3,
        "threshold": "Ausente en linea de envasado. Maximo 1 bioindicador por semana en area.",
        "plant_actions": "Instalar estanterias para empaque separadas del piso 30 cm. Reemplazar cortinas plasticas danadas. Colificar mallas enventanacion.",
        "supplier_actions": "Evaluar al proveedor de empaques para asegurar que sus instalaciones cuentan con programa MIP."
    },
    {
        "area": "Cocina / area de preparacion de alimentos",
        "keywords": ["cocina", "preparacion", "coccion", "cocina caliente", "cocina fria", "kitchen", "cooking"],
        "pest_risk": "Cucarachas (Blattella germanica) | Moscas | Roedores | Hormigas",
        "causes": "Acumulacion de grasa en campanas y ductos, restos de comida en trampas de grasa, estufas y hornallas con residuos carbonizados, basura no retirada oportunamente",
        "strategic": "Contaminacion cruzada de alimentos listos para consumo. Riesgo alto de enfermedades transmitidas por alimentos.",
        "operational": "Las campanas no se limpian con la frecuencia requerida. Los botes de basura no tienen tapa ni se lavan diariamente.",
        "severity": 5,
        "occurrence": 3,
        "threshold": "Ausente en areas de preparacion. Cero tolerancia para cucarachas y roedores.",
        "plant_actions": "Establecer programa de limpieza profunda de campanas y ductos cada 15 dias. Implementar botes de basura con pedal y tapa hermeticos. Sellar todas las rendijas y grietas en paredes y pisos.",
        "supplier_actions": "Coordinacion con proveedor de control de plagas para monitoreo intensivo en areas de cocina durante horarios de operacion."
    },
    {
        "area": "Comedor / areas de consumo",
        "keywords": ["comedor", "area de consumo", "cafeteria", "restaurante", "dining", "cafeteria"],
        "pest_risk": "Moscas (Musca domestica) | Hormigas | Roedores | Aves (Columba livia)",
        "causes": "Residuos de alimentos en mesas y pisos, ventanas sin malla, puertas abiertas al exterior, migratorios de aves en estructuras cercanas",
        "strategic": "Contaminacion de alimentos y superficies de contacto con alimentos. Mala experiencia del cliente y riesgo sanitario.",
        "operational": "La limpieza de mesas no es inmediata despues de cada uso. Las ventanas no tienen mosquitero.",
        "severity": 3,
        "occurrence": 4,
        "threshold": "Ausente en comedor. Maximo 1 mosca por hora en horario de alimentos.",
        "plant_actions": "Instalar mosquiteros en todas las ventanas. Colocar trampas de luz UV en horas de operacion. Establecer limpieza inmediata de mesas.",
        "supplier_actions": "Proveedor de control de plagas debe incluir monitoreo de aves en areas exteriores cercanas al comedor."
    },
    {
        "area": "Exteriores / perimetros",
        "keywords": ["exterior", "perimetro", "patio", "jardin", "area externa", "outside", "perimeter", "exterior"],
        "pest_risk": "Aves: Columba livia, Passer domesticus | Roedores: Rattus norvegicus | Insectos voladores",
        "causes": "Acumulacion de basura y escombros en patios, vegetacion densa contra muros, iluminacion exterior que atrae insectos nocturnos, agua estancada",
        "strategic": "Las aves y roedores del exterior son fuente constante de reintroduccion de plagas a la planta.",
        "operational": "No se poda la vegetacion perimetral. La iluminacion exterior no es de vapor de sodio (atrae menos insectos).",
        "severity": 3,
        "occurrence": 5,
        "threshold": "Estaciones de monitoreo perimetral: menos de 5 bioindicadores por mes. Ausencia de nidos de aves en estructuras.",
        "plant_actions": "Establecer programa de poda de vegetacion perimetral. Cambiar luminarias a vapor de sodio o LED. Mantener area libre de escombros y maleza.",
        "supplier_actions": "Proveedor debe realizar inspeccion perimetral semanal y emitir reporte de actividad de plagas con recomendaciones."
    },
    {
        "area": "Cuartos de servicio / instalaciones",
        "keywords": ["servicios", "instalaciones", "cisterna", "cuarto de maquinas", "caldera", "subestacion", "utility"],
        "pest_risk": "Roedores | Cucarachas | Insectos rastreros | Alacranes",
        "causes": "Falta de limpieza en cuartos de servicio, tuberias sin sellar en penetraciones de muros, acumulacion de material obsoleto",
        "strategic": "Las instalaciones de servicio actuan como refugio y via de dispersion de plagas hacia areas productivas.",
        "operational": "Los cuartos de servicio no se incluyen en el programa de limpieza regular. Hay materiales acumulados que sirven de refugio.",
        "severity": 3,
        "occurrence": 3,
        "threshold": "Ausente en interiores. Maximo 2 bioindicadores por mes en exteriores de cuartos.",
        "plant_actions": "Incluir cuartos de servicio en programa de limpieza. Sellar todas las penetraciones de tuberias en muros. Despejar materiales acumulados.",
        "supplier_actions": "Incluir cuartos de servicio en el contrato de monitoreo con estaciones de monitoreo perimetral."
    },
    {
        "area": "Drenajes y sistema de aguas residuales",
        "keywords": ["drenajes", "aguas residuales", "alcantarillado", "trampa de grasa", "canaletas", "drain", "sewer"],
        "pest_risk": "Roedores: Rattus norvegicus (rata de alcantarilla) | Cucarachas | Moscas de drenaje (Psychodidae)",
        "causes": "Drenajes sin sello hidraulico, rejillas en mal estado, acumulacion de materia organica en trampas de grasa, tuberias rotas",
        "strategic": "Las ratas de alcantarilla son vectores de leptospira, salmonella y E. coli. Las moscas de drenaje indican acumulacion de materia organica.",
        "operational": "No se realiza mantenimiento preventivo de trampas de grasa. Algunas rejillas estan rotas o no ajustan correctamente.",
        "severity": 4,
        "occurrence": 4,
        "threshold": "Ausente en drenajes internos. Rejillas en buen estado con sello hidraulico funcional.",
        "plant_actions": "Reparar o reemplazar rejillas danadas. Implementar limpieza quincenal de trampas de grasa. Verificar sello hidraulico en todos los drenajes internos.",
        "supplier_actions": "Proveedor de control de plagas debe incluir estaciones de cebado selladas en puntos de drenaje perimetral."
    }
]

def analyze_pest_risks(
    context: str,
    gate_result: dict,
    company_name: str,
    process_area: str
) -> PestAnalysisResult:
    context_lower = context.lower()
    threats = []
    threat_id_counter = 1

    for pattern in PEST_PATTERNS:
        if any(kw in context_lower for kw in pattern["keywords"]):
            severity = pattern["severity"]
            occurrence = pattern["occurrence"]
            score = severity * occurrence

            res_sev = max(1, severity - 1)
            res_occ = max(1, occurrence - 1)
            res_score = res_sev * res_occ

            threats.append(PestThreat(
                id=f"PM{threat_id_counter:03d}",
                area=pattern["area"],
                pest_risk=pattern["pest_risk"],
                potential_causes=pattern["causes"],
                strategic_approach=pattern["strategic"],
                operational_approach=pattern["operational"],
                severity=severity,
                occurrence=occurrence,
                risk_score=score,
                risk_level=get_pest_risk_level(score),
                acceptable_threshold=pattern["threshold"],
                plant_actions=pattern["plant_actions"],
                supplier_actions=pattern["supplier_actions"],
                residual_severity=res_sev,
                residual_occurrence=res_occ,
                residual_risk_score=res_score,
                residual_risk_level=get_pest_risk_level(res_score)
            ))
            threat_id_counter += 1

    high_priority_count = sum(1 for t in threats if t.risk_score >= 12)

    return PestAnalysisResult(
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
