"""
services/haccp_generator.py
Lógica de negocio: genera filas de análisis HACCP a partir de
pasos de proceso + datos de retiros FDA.

Etiquetas de PCC alineadas con el Codex Alimentarius y NOM-251:
  "Sí"
  "No (control por prerrequisitos)"
  "No (control por buenas prácticas de manufactura)"
  "No (control por saneamiento y prácticas higiénicas)"
  "No (monitoreo continuo requerido)"
"""
import logging
from models import ProcessStep, StepType, HACCPRow, FDARecall

logger = logging.getLogger("vigia.haccp_generator")

# ── Etiquetas estándar de no-PCC ──────────────────────────────────────────
_NO_PCC_PREREQ = "No (control por prerrequisitos)"
_NO_PCC_BPM    = "No (control por buenas prácticas de manufactura)"
_NO_PCC_SAN    = "No (control por saneamiento y prácticas higiénicas)"
_NO_PCC_MON    = "No (monitoreo continuo requerido)"


# ── Extracción de peligros desde retiros FDA ──────────────────────────────

_HAZARD_KEYWORDS: dict[str, str] = {
    "listeria":       "Listeria monocytogenes",
    "salmonella":     "Salmonella spp.",
    "e. coli":        "E. coli O157:H7",
    "e.coli":         "E. coli O157:H7",
    "allergen":       "Alérgenos no declarados",
    "undeclared":     "Alérgenos no declarados",
    "foreign":        "Cuerpos extraños",
    "metal":          "Fragmentos metálicos",
    "glass":          "Vidrio",
    "clostridium":    "Clostridium botulinum / perfringens",
    "staphylococcus": "Staphylococcus aureus",
    "campylobacter":  "Campylobacter spp.",
}


def extract_fda_hazards(recalls: list[FDARecall]) -> set[str]:
    hazards: set[str] = set()
    for r in recalls:
        reason = (r.reason_for_recall or "").lower()
        for keyword, canonical_name in _HAZARD_KEYWORDS.items():
            if keyword in reason:
                hazards.add(canonical_name)
    logger.info("Peligros identificados en retiros FDA: %s", hazards)
    return hazards


# ── Decisión de PCC ───────────────────────────────────────────────────────

class _PCCDecision:
    __slots__ = ("is_pcc", "pcc_label", "limite", "monitoreo", "correctiva")

    def __init__(
        self,
        is_pcc: bool,
        pcc_label: str,
        limite: str = "–",
        monitoreo: str = "",
        correctiva: str = "",
    ):
        self.is_pcc     = is_pcc
        self.pcc_label  = pcc_label
        self.limite     = limite
        self.monitoreo  = monitoreo
        self.correctiva = correctiva


def _decide_pcc(step: ProcessStep, fda_hazards: set[str]) -> _PCCDecision:
    name = step.step_name.lower()
    temp = step.time_temperature_profile.temperature_celsius

    # ── PCCs confirmados ──────────────────────────────────────────────────

    # Cocción letal
    if step.step_type == StepType.processing and temp >= 70 and (
        "cocción" in name or "coci" in name or "cook" in name
        or "horneado" in name
    ):
        return _PCCDecision(
            is_pcc=True, pcc_label="Sí",
            limite="Temperatura interna del producto ≥72 °C durante mínimo 15 s",
            monitoreo=(
                "Medición continua de temperatura interna con termopar en el "
                "punto más frío del producto, cada lote"
            ),
            correctiva=(
                "Si T <72 °C: extender cocción y re-verificar. "
                "Si falla técnica persiste: desechar lote y registrar desviación"
            ),
        )

    # Pasteurización standalone (e.g. lácteos)
    if step.step_type == StepType.processing and (
        "pasteurización" in name or "pasteuriz" in name
    ) and "post-envasado" not in name and "tpp" not in name:
        return _PCCDecision(
            is_pcc=True, pcc_label="Sí",
            limite=(
                "HTST: ≥72 °C durante 15 s — o — "
                "LTLT: ≥63 °C durante 30 min"
            ),
            monitoreo=(
                "Medición continua de temperatura y tiempo "
                "(termógrafo o cronómetro calibrado), cada lote"
            ),
            correctiva=(
                "Si no se alcanza límite: recalcular tiempo o repasteurizar. "
                "Si persiste fallo técnico: desechar lote"
            ),
        )

    # Enfriamiento rápido con Listeria confirmada por FDA
    if step.step_type == StepType.processing and (
        "enfriamiento" in name or "enfría" in name or "cool" in name or "abatidor" in name
    ):
        if "Listeria monocytogenes" in fda_hazards:
            return _PCCDecision(
                is_pcc=True, pcc_label="Sí",
                limite="De 72 °C a ≤10 °C en ≤2 h (zona de peligro 10–60 °C)",
                monitoreo=(
                    "Temperatura interna del producto cada 15 min durante "
                    "enfriamiento en túnel o abatidor"
                ),
                correctiva=(
                    "Si tiempo >2 h o T final >10 °C: desviar lote a "
                    "reevaluación microbiológica antes de continuar proceso"
                ),
            )

    # Tratamiento térmico post-envasado (TPP)
    if step.step_type == StepType.processing and (
        "post-envasado" in name or "tpp" in name
    ):
        if "Listeria monocytogenes" in fda_hazards:
            return _PCCDecision(
                is_pcc=True, pcc_label="Sí",
                limite="Baño maría 83–87 °C durante ≥30 min (reducción ≥5 log Listeria)",
                monitoreo=(
                    "Temperatura del baño maría continua + tiempo de inmersión "
                    "por lote con datalogger"
                ),
                correctiva=(
                    "Si T <83 °C o tiempo <30 min: extender tratamiento y re-verificar. "
                    "Si falla persistente: desechar lote"
                ),
            )

    # Detector de metales
    if "detector" in name and "metal" in name:
        return _PCCDecision(
            is_pcc=True, pcc_label="Sí",
            limite="Detección de Fe ≥2.5 mm, No-Fe ≥3.0 mm, Acero inox ≥3.5 mm",
            monitoreo=(
                "Verificación con estándares certificados al inicio, mitad y fin "
                "de cada turno. Registro de cada pieza rechazada"
            ),
            correctiva=(
                "Si falla la verificación: detener línea, retener producto desde "
                "última verificación exitosa, re-inspección manual"
            ),
        )

    # Fermentación / control de pH
    if any(k in name for k in ("fermentación", "ferment", "inoculación")):
        return _PCCDecision(
            is_pcc=True, pcc_label="Sí",
            limite=(
                "pH final del producto ≤4.6 (inhibe patógenos). "
                "Temperatura de incubación 42–44 °C"
            ),
            monitoreo=(
                "pH-metro calibrado cada 30 min durante fermentación; "
                "control continuo de temperatura de incubación"
            ),
            correctiva=(
                "Si pH >4.6 a las 6 h: extender fermentación o re-inocular. "
                "Si pH no baja en 2 h adicionales: desechar lote"
            ),
        )

    # ── No-PCCs con etiqueta contextual ──────────────────────────────────

    if step.step_type == StepType.receiving:
        return _PCCDecision(is_pcc=False, pcc_label=_NO_PCC_PREREQ)

    if step.step_type == StepType.storage:
        temp_limit = step.time_temperature_profile.temperature_celsius or 4.0
        return _PCCDecision(
            is_pcc=False, pcc_label=_NO_PCC_MON,
            limite=f"Temperatura máxima del producto ≤{int(temp_limit + 2)} °C",
        )

    if step.step_type == StepType.preparation:
        return _PCCDecision(is_pcc=False, pcc_label=_NO_PCC_SAN)

    if step.step_type == StepType.packaging:
        return _PCCDecision(is_pcc=False, pcc_label=_NO_PCC_PREREQ)

    if step.step_type == StepType.distribution:
        return _PCCDecision(
            is_pcc=False, pcc_label=_NO_PCC_MON,
            limite="Temperatura máxima del producto ≤8 °C durante transporte",
        )

    return _PCCDecision(is_pcc=False, pcc_label=_NO_PCC_BPM)


# ── Generación de campos ──────────────────────────────────────────────────

def _hazard_text(step: ProcessStep, fda_hazards: set[str]) -> str:
    name = step.step_name.lower()
    bio, quim, fis = [], [], []

    if step.step_type == StepType.receiving:
        bio  = ["Salmonella spp.", "E. coli O157:H7", "Listeria monocytogenes", "esporas de Bacillus cereus"]
        quim = ["Residuos de antibióticos / pesticidas", "nitritos excesivos"]
        fis  = ["Cuerpos extraños (huesos, plásticos de empaque proveedor)"]

    elif step.step_type == StepType.storage:
        bio  = ["Listeria monocytogenes (crecimiento si T >4 °C)", "Salmonella spp."]
        quim = ["Desarrollo de toxinas bacterianas por temperatura inadecuada", "oxidación lipídica"]

    elif step.step_type == StepType.preparation:
        bio  = ["Listeria monocytogenes (contaminación cruzada por superficies o personal)"]
        fis  = ["Fragmentos metálicos de cuchillas / mezcladora"]

    elif step.step_type == StepType.processing:
        if any(k in name for k in ("cocción", "cook", "horneado")):
            bio  = ["Salmonella spp. (supervivencia)", "E. coli (supervivencia)", "Listeria monocytogenes (supervivencia)"]
            quim = ["Formación de nitrosaminas (exceso de nitrito + calor)"]
        elif any(k in name for k in ("pasteuriz",)):
            bio  = ["Salmonella spp.", "Listeria monocytogenes", "E. coli", "Coxiella burnetii"]
            quim = ["Inactivación insuficiente de enzimas (fosfatasa alcalina)"]
        elif any(k in name for k in ("enfriamiento", "abatidor", "cool")):
            bio  = ["Listeria monocytogenes (crecimiento en zona de peligro 10–60 °C)", "Clostridium perfringens"]
            fis  = ["Contaminación por condensado de equipos"]
        elif any(k in name for k in ("post-envasado", "tpp")):
            bio  = ["Listeria monocytogenes (supervivencia post-envasado)"]
        elif "detector" in name:
            fis  = ["Fragmentos metálicos (Fe, No-Fe, Acero inoxidable)"]
        elif any(k in name for k in ("fermentación", "inoculación")):
            bio  = ["Crecimiento de patógenos si cultivo starter no domina (Listeria, Yersinia)"]
            quim = ["Producción de etanol o CO₂ por levaduras contaminantes"]
            fis  = ["Contaminación por malas prácticas de manipulación"]
        elif any(k in name for k in ("mezcla", "formula", "dosificación")):
            quim = ["Error de formulación (exceso de aditivos / alérgenos no declarados)"]
            bio  = ["Staphylococcus aureus (manipulación excesiva)"]

    elif step.step_type == StepType.packaging:
        bio  = ["Listeria monocytogenes (recontaminación post-cocción)", "mohos y levaduras (ambiente)"]
        fis  = ["Sellos defectuosos (pérdida de vacío / hermeticidad)", "fragmentos de envase"]

    elif step.step_type == StepType.distribution:
        bio  = ["Listeria monocytogenes (crecimiento por ruptura de cadena de frío)", "Pseudomonas spp. (psicrótrofos)"]

    def _annotate(lst: list[str]) -> list[str]:
        return [
            f"{h} ⚠️ confirmado en retiros FDA"
            if any(h.split()[0].lower() in fda_h.lower() for fda_h in fda_hazards)
            else h
            for h in lst
        ]

    parts = []
    if bio:  parts.append("Biológico: " + ", ".join(_annotate(bio)))
    if quim: parts.append("Químico: "   + ", ".join(quim))
    if fis:  parts.append("Físico: "    + ", ".join(fis))
    return ". ".join(parts) if parts else "Sin peligros significativos identificados"


def _preventive_measures(step: ProcessStep) -> str:
    name = step.step_name.lower()
    temp = step.time_temperature_profile.temperature_celsius

    if step.step_type == StepType.receiving:
        return (
            "Proveedores aprobados con certificación TIF/BRC; "
            "certificado de análisis por lote; inspección visual y olfativa; "
            "control de temperatura en recepción (≤4 °C)"
        )
    if step.step_type == StepType.storage:
        t = f"≤{int(temp)} °C" if temp else "≤4 °C"
        return f"Refrigeración {t}; rotación FIFO; uso de M.P. en <48 h; calibración de sensores"
    if step.step_type == StepType.preparation:
        return (
            "Limpieza y saneamiento de superficies y equipos previo a uso; "
            "uso de EPP (guantes, cubrebocas, cofia); "
            "detector de metales en línea; capacitación en higiene personal"
        )
    if step.step_type == StepType.processing:
        if any(k in name for k in ("cocción", "cook", "horneado")):
            return "Cocción a ≥72 °C interno durante ≥15 s; control de dosis de nitrito sódico (≤200 ppm NOM-213)"
        if "pasteuriz" in name and "post" not in name:
            return "Tiempo/temperatura adecuados (HTST: 72 °C/15 s o LTLT: 63 °C/30 min)"
        if any(k in name for k in ("enfriamiento", "abatidor")):
            return "Enfriamiento rápido: 72 °C → ≤10 °C en ≤2 h; túnel/abatidor con circulación de aire frío"
        if any(k in name for k in ("post-envasado", "tpp")):
            return "TPP en baño maría: 85 °C durante ≥30 min; reducción ≥5 log de Listeria (validado)"
        if "detector" in name:
            return "Detector de metales calibrado; verificación con estándares al inicio de turno; sistema de rechazo automático"
        if any(k in name for k in ("fermentación", "inoculación")):
            return (
                "Añadir cultivo iniciador activo certificado (Lactobacillus, Streptococcus); "
                "mantener temperatura de incubación 42–44 °C; monitoreo de pH hasta ≤4.6"
            )
        if any(k in name for k in ("mezcla", "dosificación", "llenado")):
            return "Área limpia o línea cerrada; saneamiento de dosificador; manipulación mínima del producto"
    if step.step_type == StepType.packaging:
        return (
            "Envasado en área de alto riesgo con control ambiental; "
            "saneamiento de termoformadora; verificación de sellado hermético"
        )
    if step.step_type == StepType.distribution:
        return "Unidades refrigeradas (≤4 °C); registro de temperatura continuo (datalogger); cadena de frío documentada"
    return "Buenas Prácticas de Manufactura (BPM) generales"


def _monitoring(step: ProcessStep, is_pcc: bool, pcc_decision: _PCCDecision) -> str:
    if is_pcc:
        return pcc_decision.monitoreo
    name = step.step_name.lower()
    if step.step_type == StepType.receiving:
        return "Inspección visual + temperatura en cada recepción; revisión de certificados por lote"
    if step.step_type == StepType.storage:
        return "Sensor de temperatura con registro continuo (cada 15 min); revisión visual cada turno"
    if step.step_type == StepType.preparation:
        return "Inspección visual de limpieza al inicio de turno; verificación del detector de metales con estándar"
    if step.step_type == StepType.packaging:
        return "Verificación visual de sellos cada 30 min; prueba de hermeticidad por inmersión cada hora"
    if step.step_type == StepType.distribution:
        return "Lectura del datalogger de temperatura al despacho y al punto de entrega"
    if any(k in name for k in ("mezcla", "dosificación", "llenado", "envasado")):
        return "Temperatura de la mezcla/producto al llenar; tiempo de exposición fuera de refrigeración"
    if any(k in name for k in ("enfriamiento", "abatidor")):
        return "Temperatura de salida del enfriador / abatidor al final del proceso"
    return "Inspección visual al inicio de cada turno"


def _corrective(step: ProcessStep, is_pcc: bool, pcc_decision: _PCCDecision) -> str:
    if is_pcc:
        return pcc_decision.correctiva
    if step.step_type == StepType.receiving:
        return (
            "Rechazar partida si T >7 °C, olor anómalo, certificado ausente "
            "o cuerpos extraños visibles. Documentar y notificar a proveedor"
        )
    if step.step_type == StepType.storage:
        return (
            "Ajustar refrigeración de inmediato; desviar M.P. a uso urgente si T >4 °C por >2 h; "
            "evaluar disposición del lote con base en tiempo/temperatura acumulada"
        )
    if step.step_type == StepType.preparation:
        return (
            "Detener línea y re-sanitizar si se detecta contaminación visible; "
            "retener lote si detector de metales activa alarma"
        )
    if step.step_type == StepType.packaging:
        return (
            "Rechazar envases con sellos defectuosos; ajustar parámetros de sellado; "
            "re-sanitizar si se detecta contaminación ambiental"
        )
    if step.step_type == StepType.distribution:
        return "Rechazar producto si T >8 °C durante más de 2 h acumuladas; evaluación microbiológica antes de comercialización"
    return "Corregir condición fuera de estándar, documentar y notificar a supervisor"


def _verification(step: ProcessStep, is_pcc: bool) -> str:
    name = step.step_name.lower()
    if is_pcc:
        if any(k in name for k in ("cocción", "cook", "horneado")):
            return (
                "Calibración de termómetros diaria con patrón NIST; "
                "verificación semanal con termógrafo; análisis de nitritos en P.T. (trimestral)"
            )
        if "pasteuriz" in name and "post" not in name:
            return (
                "Verificación semanal con prueba de fosfatasa alcalina (resultado negativo). "
                "Calibración de termómetros diaria"
            )
        if any(k in name for k in ("enfriamiento", "abatidor")):
            return "Validación anual del perfil tiempo-temperatura; calibración de sensores mensual"
        if any(k in name for k in ("post-envasado", "tpp")):
            return "Validación inicial con inoculado de Listeria innocua (≥5 log); calibración semanal"
        if "detector" in name:
            return "Calibración con estándares certificados al inicio y fin de turno; prueba de desafío mensual"
        if any(k in name for k in ("fermentación", "inoculación")):
            return "Verificación con cultivo patrón semanal; calibración de pH-metro diaria"
    if step.step_type == StepType.receiving:
        return "Auditoría anual de proveedores; análisis periódicos de calidad (antibióticos, residuos)"
    if step.step_type == StepType.storage:
        return "Calibración mensual de termómetros; revisión semanal de registros de temperatura"
    if step.step_type == StepType.preparation:
        return "Hisopado microbiológico de superficies semanal (Listeria spp.); verificación del detector con Fe 2.0 mm c/turno"
    if step.step_type == StepType.packaging:
        return "Programa de control ambiental de Listeria (zonas 1–3) semanal; prueba de hermeticidad al inicio de turno"
    if step.step_type == StepType.distribution:
        return "Auditoría de transportistas semestral; verificación de calibración de dataloggers"
    return "Revisión de registros por supervisor semanal; auditoría interna mensual"


def _records(step: ProcessStep, is_pcc: bool) -> str:
    n    = step.step_number
    name = step.step_name.lower()
    if is_pcc:
        if any(k in name for k in ("cocción", "cook", "horneado")):
            return f"F-PCC-{n:02d}-COC: Gráfica cocción (T/t) por lote; Certificado análisis nitritos"
        if "pasteuriz" in name and "post" not in name:
            return f"F-PCC-{n:02d}-PAS: Gráfica de pasteurización (T/t); Registro temperatura/tiempo por lote"
        if any(k in name for k in ("enfriamiento", "abatidor")):
            return f"F-PCC-{n:02d}-ENF: Curva de enfriamiento por lote; Reporte de desviaciones"
        if any(k in name for k in ("post-envasado", "tpp")):
            return f"F-PCC-{n:02d}-TPP: Gráfica baño maría; Tiempo de inmersión; Validación microbiológica"
        if "detector" in name:
            return f"F-PCC-{n:02d}-DET: Verificación detector (inicio/fin turno); Registro de rechazos"
        if any(k in name for k in ("fermentación", "inoculación")):
            return f"F-PCC-{n:02d}-FERM: Curva de pH vs. tiempo; Registro de temperatura de incubación"
    if step.step_type == StepType.receiving:
        return f"F-REC-{n:02d}: Certificado sanitario proveedor; Hoja inspección M.P.; Registro T° recepción"
    if step.step_type == StepType.storage:
        return f"F-ALM-{n:02d}: Gráfica continua T° cámara; Bitácora FIFO; Registro desviaciones"
    if step.step_type == StepType.preparation:
        return f"F-PREP-{n:02d}: Hoja saneamiento equipos; Verificación detector metales; Análisis microbiológico superficies"
    if step.step_type == StepType.packaging:
        return f"F-ENV-{n:02d}: Registro calidad sellado; Control ambiental Listeria; Ajustes máquina"
    if step.step_type == StepType.distribution:
        return f"F-DIST-{n:02d}: Reporte datalogger por viaje; Registro T° despacho y entrega"
    return f"F-GEN-{n:02d}: Registro de control general"


# ── Punto de entrada ──────────────────────────────────────────────────────

def generate_haccp_rows(
    steps: list[ProcessStep],
    fda_hazards: set[str],
) -> list[HACCPRow]:
    rows: list[HACCPRow] = []
    for step in steps:
        pcc_dec = _decide_pcc(step, fda_hazards)
        row = HACCPRow(
            etapa             = f"{step.step_number}. {step.step_name}",
            peligro           = _hazard_text(step, fda_hazards),
            medida_preventiva = _preventive_measures(step),
            es_pcc            = pcc_dec.is_pcc,
            pcc_label         = pcc_dec.pcc_label,
            limite_critico    = pcc_dec.limite,
            monitoreo         = _monitoring(step, pcc_dec.is_pcc, pcc_dec),
            accion_correctiva = _corrective(step, pcc_dec.is_pcc, pcc_dec),
            verificacion      = _verification(step, pcc_dec.is_pcc),
            registro          = _records(step, pcc_dec.is_pcc),
        )
        rows.append(row)
        logger.debug("Etapa %d '%s' → %s", step.step_number, step.step_name, pcc_dec.pcc_label)
    return rows
