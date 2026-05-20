"""
server.py — VIGÍA HACCP MCP Server
Transporte: SSE (compatible con SurfSense y cualquier cliente MCP estándar)

Herramientas expuestas:
  1. get_process_step_schema  — devuelve el schema JSON para que el LLM sepa cómo
                                estructurar los pasos de proceso extraídos de la KB
  2. search_fda_recalls       — búsqueda directa en openFDA (diagnóstico / enriquecimiento)
  3. generate_haccp_analysis  — análisis HACCP completo → JSON + guarda Excel
"""
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from services.openfda import OpenFDAClient
from services.haccp_generator import extract_fda_hazards, generate_haccp_rows
from exporters.excel_exporter import export_to_excel
from services.food_fraud_service import (
    validate_context as vf_validate_context, 
    get_fraud_reference_data as vf_get_reference, 
    analyze_fraud_threats as vf_analyze_threats
)
from exporters.food_fraud_exporter import export_food_fraud_xlsx
from services.food_defense_service import analyze_food_defense as vf_analyze_defense
from exporters.food_defense_exporter import export_food_defense_xlsx
from services.environmental_monitoring_service import (
    validate_context as em_validate_context,
    analyze_environmental_risks as em_analyze_risks
)
from exporters.environmental_monitoring_exporter import export_environmental_monitoring_xlsx
from services.pest_management_service import (
    validate_context as pm_validate_context,
    analyze_pest_risks as pm_analyze_risks
)
from exporters.pest_management_exporter import export_pest_management_xlsx
from models import (
    ProcessStep, TimeTemperatureProfile, StepType, FraudThreat, DefenseThreat,
    EnvironmentalThreat, PestThreat, AllergenThreat 
)

# ── Configuración ─────────────────────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.getLevelName(os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vigia.server")

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/vigia_outputs"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Servidor MCP ──────────────────────────────────────────────────────────
mcp = FastMCP(
    name="VIGÍA HACCP",
    instructions=(
        "Servidor MCP de análisis HACCP para la plataforma VIGÍA. "
        "Genera planes HACCP completos (NOM-251, Codex Alimentarius) "
        "enriquecidos con retiros reales de la FDA. "
        "Exporta resultados en Excel con formato profesional."
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# HERRAMIENTA 1: Schema de referencia
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_process_step_schema() -> str:
    """
    Devuelve el schema JSON que debes usar para construir la lista de pasos
    de proceso antes de llamar a generate_haccp_analysis.

    Úsala PRIMERO cuando el usuario quiera generar un análisis HACCP,
    para saber exactamente qué campos necesitas extraer de la base de
    conocimiento del cliente.

    Retorna: JSON con el schema y un ejemplo completo.
    """
    schema = {
        "description": (
            "Cada elemento de la lista 'process_steps' representa una etapa "
            "del proceso productivo del cliente."
        ),
        "step_type_values": [t.value for t in StepType],
        "schema": {
            "step_number": "int — número de orden de la etapa (1, 2, 3…)",
            "step_name":   "str — nombre descriptivo de la etapa (ej: 'Cocción en horno')",
            "step_type":   f"str — uno de: {[t.value for t in StepType]}",
            "time_temperature_profile": {
                "temperature_celsius": "float — temperatura de operación (0 si no aplica)",
                "duration_minutes":    "float | null — duración en minutos (null si no aplica)",
                "target_unit":         "str | null — qué se controla (ej: 'producto interno', 'ambiente')",
            },
            "notes": "str | null — observaciones adicionales del cliente",
        },
        "example": [
            {
                "step_number": 1,
                "step_name": "Recepción de materia prima cárnica",
                "step_type": "receiving",
                "time_temperature_profile": {
                    "temperature_celsius": 4.0,
                    "duration_minutes": None,
                    "target_unit": "producto recibido",
                },
                "notes": "Proveedor TIF certificado. Se recibe en cajas de cartón corrugado.",
            },
            {
                "step_number": 2,
                "step_name": "Almacenamiento en refrigeración",
                "step_type": "storage",
                "time_temperature_profile": {
                    "temperature_celsius": 2.0,
                    "duration_minutes": None,
                    "target_unit": "cámara frigorífica",
                },
                "notes": None,
            },
            {
                "step_number": 3,
                "step_name": "Cocción en horno de vapor",
                "step_type": "processing",
                "time_temperature_profile": {
                    "temperature_celsius": 85.0,
                    "duration_minutes": 45.0,
                    "target_unit": "temperatura interna del producto",
                },
                "notes": "El punto más frío del producto debe alcanzar ≥72 °C.",
            },
            {
                "step_number": 4,
                "step_name": "Enfriamiento en abatidor",
                "step_type": "processing",
                "time_temperature_profile": {
                    "temperature_celsius": 4.0,
                    "duration_minutes": 90.0,
                    "target_unit": "temperatura interna del producto",
                },
                "notes": None,
            },
            {
                "step_number": 5,
                "step_name": "Envasado al vacío en termoformadora",
                "step_type": "packaging",
                "time_temperature_profile": {
                    "temperature_celsius": 10.0,
                    "duration_minutes": None,
                    "target_unit": "temperatura ambiente del área",
                },
                "notes": None,
            },
        ],
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# HERRAMIENTA 2: Búsqueda en openFDA
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def search_fda_data(
    product_name: str,
    hazard_types: str = "",
    years: int = 5,
) -> str:
    """
    Busca retiros de mercado (Recalls) y reportes de eventos adversos (CAERS) 
    en la base de datos de la FDA para el producto especificado.

    Args:
        product_name:  Nombre del producto o ingrediente (ej: "milk", "cheese").
                       Usa términos en inglés para mejores resultados.
        hazard_types:  Peligros a buscar en retiros, separados por coma 
                       (ej: "Listeria, Salmonella").
        years:         Número de años hacia atrás para la búsqueda (defecto: 5).

    Retorna: JSON con retiros y eventos adversos encontrados.
    """
    fda = OpenFDAClient()
    areas = [h.strip() for h in hazard_types.split(",") if h.strip()]

    try:
        recalls = await fda.fetch_recalls(product_name, areas, limit=15, years=years)
        events  = await fda.fetch_adverse_events(product_name, limit=15, years=years)
    except Exception as exc:
        logger.error("Error consultando openFDA: %s", exc)
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    hazards = extract_fda_hazards(recalls)

    result = {
        "summary": {
            "product": product_name,
            "years_searched": years,
            "total_recalls": len(recalls),
            "total_adverse_events": len(events),
            "detected_hazards_in_recalls": sorted(hazards),
        },
        "recalls": [
            {
                "id": r.recall_number,
                "firm": r.recalling_firm,
                "description": r.product_description[:200],
                "reason": r.reason_for_recall[:200],
                "date": r.recall_initiation_date,
            }
            for r in recalls
        ],
        "adverse_events": [
            {
                "id": e.report_number,
                "date": e.date_created,
                "outcomes": e.outcomes,
                "reactions": e.reactions,
                "products": e.product_names,
            }
            for e in events
        ],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# HERRAMIENTA 3: Análisis HACCP completo
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def generate_haccp_analysis(
    product_name: str,
    process_steps_json: str,
    focus_areas: str = "",
    fda_product_keyword: str = "",
) -> str:
    """
    Genera un análisis HACCP completo para el producto y flujo de proceso indicados.
    Enriquece el análisis con datos reales de retiros de mercado de la FDA.
    Guarda el resultado en un archivo Excel con formato profesional.

    Úsala cuando el usuario quiera generar o completar un Plan HACCP.
    ANTES de llamar a esta herramienta, usa get_process_step_schema para conocer
    el formato exacto de process_steps_json.

    Args:
        product_name:
            Nombre comercial del producto final
            (ej: "Jamón cocido rebanado", "Queso Oaxaca").

        process_steps_json:
            Lista de etapas del proceso en formato JSON (string).
            Debe seguir el schema devuelto por get_process_step_schema.
            Ejemplo: '[{"step_number":1,"step_name":"Recepción","step_type":"receiving",...}]'

        focus_areas:
            Peligros de interés específicos separados por coma
            (ej: "Listeria, Salmonella, allergen").
            Se usan para búsqueda dirigida en openFDA.

        fda_product_keyword:
            Palabra clave en INGLÉS para buscar retiros en openFDA.
            Si se deja vacío se usa el product_name directamente.
            Ej: si product_name es "Jamón cocido", usar "cooked ham".

    Retorna:
        JSON con:
        - resumen del análisis (número de PCCs, peligros FDA)
        - tabla HACCP completa fila por fila
        - ruta del archivo Excel generado
        - lista de retiros FDA consultados
    """
    # ── 1. Parsear pasos de proceso ──────────────────────────────────────
    try:
        raw_steps = json.loads(process_steps_json)
        if not isinstance(raw_steps, list) or len(raw_steps) == 0:
            return json.dumps({
                "error": "process_steps_json debe ser una lista JSON no vacía."
            }, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "error": f"JSON inválido en process_steps_json: {exc}"
        }, ensure_ascii=False)

    try:
        steps: list[ProcessStep] = []
        for raw in raw_steps:
            ttp_raw = raw.get("time_temperature_profile", {})
            ttp = TimeTemperatureProfile(
                temperature_celsius = ttp_raw.get("temperature_celsius", 0.0),
                duration_minutes    = ttp_raw.get("duration_minutes"),
                target_unit         = ttp_raw.get("target_unit"),
            )
            steps.append(ProcessStep(
                step_number             = raw["step_number"],
                step_name               = raw["step_name"],
                step_type               = StepType(raw["step_type"]),
                time_temperature_profile = ttp,
                notes                   = raw.get("notes"),
            ))
    except (KeyError, ValueError) as exc:
        return json.dumps({
            "error": f"Error al parsear pasos de proceso: {exc}. "
                     "Verifica que cada step tenga step_number, step_name y step_type válido."
        }, ensure_ascii=False)

    # ── 2. Consultar openFDA ─────────────────────────────────────────────
    fda_keyword = fda_product_keyword.strip() or product_name
    areas       = [a.strip() for a in focus_areas.split(",") if a.strip()]
    fda_client  = OpenFDAClient()

    try:
        # Buscamos retiros y eventos adversos (últimos 5 años por defecto en fetch_recalls/fetch_adverse_events)
        recalls = await fda_client.fetch_recalls(fda_keyword, areas, limit=10)
        events  = await fda_client.fetch_adverse_events(fda_keyword, limit=10)
    except Exception as exc:
        logger.warning("openFDA falló, continuando sin datos FDA: %s", exc)
        recalls = []
        events  = []

    fda_hazards = extract_fda_hazards(recalls)

    # ── 3. Generar tabla HACCP ───────────────────────────────────────────
    haccp_rows = generate_haccp_rows(steps, fda_hazards)
    pcc_steps  = [r for r in haccp_rows if r.es_pcc]

    # ── 4. Exportar a Excel ──────────────────────────────────────────────
    try:
        excel_path = export_to_excel(
            product_name = product_name,
            haccp_rows   = haccp_rows,
            fda_recalls  = recalls,
            fda_hazards  = fda_hazards,
            output_dir   = OUTPUT_DIR,
        )
        excel_str = str(excel_path)
    except Exception as exc:
        logger.error("Error generando Excel: %s", exc)
        excel_str = f"Error al generar Excel: {exc}"

    # ── 5. Construir respuesta ───────────────────────────────────────────
    result = {
        "status": "success",
        "summary": {
            "product_name":        product_name,
            "total_steps":         len(haccp_rows),
            "total_pccs":          len(pcc_steps),
            "pcc_steps":           [r.etapa for r in pcc_steps],
            "fda_hazards_found":   sorted(fda_hazards),
            "fda_recalls_used":    len(recalls),
            "fda_events_found":    len(events),
            "excel_file":          excel_str,
        },
        "haccp_table": [
            {
                "etapa":             r.etapa,
                "peligro":           r.peligro,
                "medida_preventiva": r.medida_preventiva,
                "es_pcc":            r.es_pcc,
                "limite_critico":    r.limite_critico,
                "monitoreo":         r.monitoreo,
                "accion_correctiva": r.accion_correctiva,
                "verificacion":      r.verificacion,
                "registro":          r.registro,
            }
            for r in haccp_rows
        ],
        "fda_recalls": [
            {
                "recall_number": r.recall_number,
                "firm":          r.recalling_firm,
                "reason":        r.reason_for_recall[:150],
                "date":          r.recall_initiation_date,
                "class":         r.classification,
            }
            for r in recalls[:10]
        ],
        "fda_adverse_events": [
            {
                "id":        e.report_number,
                "date":      e.date_created,
                "reactions": e.reactions,
                "outcomes":  e.outcomes,
            }
            for e in events[:10]
        ]
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# FOOD FRAUD TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def validate_context(available_context: str) -> str:
    """
    Tool de validación obligatoria (context gate). Debe llamarse siempre antes de cualquier análisis.
    Evalúa si el contexto disponible cubre los 5 requisitos mínimos.
    """
    result = vf_validate_context(available_context)
    return result.model_dump_json()


@mcp.tool()
def get_fraud_reference_data(ingredient: str) -> str:
    """
    Consulta la base de datos local de adulteraciones conocidas para un ingrediente específico.
    """
    result = vf_get_reference(ingredient)
    return result.model_dump_json()


@mcp.tool()
def analyze_fraud_threats(
    context: str,
    gate_result_json: str,
    company_name: str,
    process_area: str
) -> str:
    """
    Identifica las amenazas de fraude alimentario y asigna valores de Severidad y Ocurrencia.
    """
    try:
        gate_result = json.loads(gate_result_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "gate_result_json must be a valid JSON string"})

    result = vf_analyze_threats(context, gate_result, company_name, process_area)
    return result.model_dump_json()


@mcp.tool()
def generate_food_fraud_xlsx(
    threats_json: str,
    company_name: str,
    process_area: str,
    evaluator_name: str,
    evaluation_date: str,
    gate_result_json: str,
    analysis_metadata_json: str
) -> str:
    """
    Genera el archivo XLSX con el formato oficial de análisis de fraude alimentario.
    """
    try:
        threats_raw = json.loads(threats_json)
        threats = [FraudThreat(**t) for t in threats_raw]
        gate_result = json.loads(gate_result_json)
        analysis_metadata = json.loads(analysis_metadata_json)
    except Exception as e:
        return json.dumps({"error": f"Error parsing inputs: {str(e)}"})

    result = export_food_fraud_xlsx(
        threats=threats,
        company_name=company_name,
        process_area=process_area,
        evaluator_name=evaluator_name,
        evaluation_date=evaluation_date,
        gate_result=gate_result,
        analysis_metadata=analysis_metadata,
        output_dir=OUTPUT_DIR
    )
    return result.model_dump_json()


@mcp.tool()
def analyze_food_defense(
    context: str,
    company_name: str,
    process_area: str
) -> str:
    """
    Realiza un análisis de vulnerabilidades de Food Defense (actos dolosos, sabotaje).
    Identifica amenazas en áreas sensibles y calcula el nivel de riesgo MRO.
    """
    result = vf_analyze_defense(context, company_name, process_area)
    return result.model_dump_json()


@mcp.tool()
def generate_food_defense_xlsx(
    threats_json: str,
    company_name: str,
    process_area: str
) -> str:
    """
    Genera el archivo XLSX con el formato oficial MRO de Food Defense.
    """
    try:
        threats_raw = json.loads(threats_json)
        threats = [DefenseThreat(**t) for t in threats_raw]
    except Exception as e:
        return json.dumps({"error": f"Error parsing inputs: {str(e)}"})

    result = export_food_defense_xlsx(
        threats=threats,
        company_name=company_name,
        process_area=process_area,
        output_dir=OUTPUT_DIR
    )
    return result.model_dump_json()


# ═══════════════════════════════════════════════════════════════════════════
# ENVIRONMENTAL MONITORING TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def validate_environmental_context(available_context: str) -> str:
    """
    Tool de validacion obligatoria (context gate) para Monitoreo Ambiental.
    Debe llamarse siempre antes de cualquier analisis.
    Evalua si el contexto disponible cubre los 5 requisitos minimos.
    """
    result = em_validate_context(available_context)
    return result.model_dump_json()


@mcp.tool()
def analyze_environmental_risks(
    context: str,
    gate_result_json: str,
    company_name: str,
    process_area: str
) -> str:
    """
    Identifica los riesgos microbiologicos ambientales por area de proceso
    y asigna valores de Severidad y Ocurrencia segun la metodologia MRO.
    """
    try:
        gate_result = json.loads(gate_result_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "gate_result_json must be a valid JSON string"})

    result = em_analyze_risks(context, gate_result, company_name, process_area)
    return result.model_dump_json()


@mcp.tool()
def generate_environmental_monitoring_xlsx(
    threats_json: str,
    company_name: str,
    process_area: str,
    gate_result_json: str
) -> str:
    """
    Genera el archivo XLSX con el formato oficial de Analisis de Riesgo
    de Monitoreo Ambiental Microbiologico.
    """
    try:
        threats_raw = json.loads(threats_json)
        threats = [EnvironmentalThreat(**t) for t in threats_raw]
        gate_result = json.loads(gate_result_json)
    except Exception as e:
        return json.dumps({"error": f"Error parsing inputs: {str(e)}"})

    result = export_environmental_monitoring_xlsx(
        threats=threats,
        company_name=company_name,
        process_area=process_area,
        gate_result=gate_result,
        output_dir=OUTPUT_DIR
    )
    return result.model_dump_json()


# ═══════════════════════════════════════════════════════════════════════════
# PEST MANAGEMENT (MIP) TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def validate_pest_context(available_context: str) -> str:
    """
    Tool de validacion obligatoria (context gate) para Control de Plagas (MIP).
    Debe llamarse siempre antes de cualquier analisis.
    Evalua si el contexto disponible cubre los 5 requisitos minimos.
    """
    result = pm_validate_context(available_context)
    return result.model_dump_json()


@mcp.tool()
def analyze_pest_risks(
    context: str,
    gate_result_json: str,
    company_name: str,
    process_area: str
) -> str:
    """
    Identifica los riesgos de plagas por area operativa de la planta
    y asigna valores de Severidad y Ocurrencia segun la matriz 5x5.
    """
    try:
        gate_result = json.loads(gate_result_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "gate_result_json must be a valid JSON string"})

    result = pm_analyze_risks(context, gate_result, company_name, process_area)
    return result.model_dump_json()


@mcp.tool()
def generate_pest_management_xlsx(
    threats_json: str,
    company_name: str,
    process_area: str,
    gate_result_json: str
) -> str:
    """
    Genera el archivo XLSX con el formato oficial de Analisis de Riesgo
    del programa de Control de Plagas (MIP).
    """
    try:
        threats_raw = json.loads(threats_json)
        threats = [PestThreat(**t) for t in threats_raw]
        gate_result = json.loads(gate_result_json)
    except Exception as e:
        return json.dumps({"error": f"Error parsing inputs: {str(e)}"})

    result = export_pest_management_xlsx(
        threats=threats,
        company_name=company_name,
        process_area=process_area,
        gate_result=gate_result,
        output_dir=OUTPUT_DIR
    )
    return result.model_dump_json()


from services.allergen_management_service import (
    validate_context as al_validate_context,
    analyze_allergen_risks as al_analyze_risks
)
from exporters.allergen_management_exporter import export_allergen_management_xlsx


# ═══════════════════════════════════════════════════════════════════════════
# ALLERGEN MANAGEMENT TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
def validate_allergen_context(available_context: str) -> str:
    """
    Tool de validacion obligatoria (context gate) para Gestion de Alergenos.
    Debe llamarse siempre antes de cualquier analisis.
    Evalua si el contexto disponible cubre los 5 requisitos minimos.
    """
    result = al_validate_context(available_context)
    return result.model_dump_json()


@mcp.tool()
def analyze_allergen_risks(
    context: str,
    gate_result_json: str,
    company_name: str,
    process_area: str
) -> str:
    """
    Identifica los riesgos de contacto cruzado de alergenos por area
    y asigna valores de Severidad (I-IV) y Ocurrencia (A-E) segun matriz GFSI.
    """
    try:
        gate_result = json.loads(gate_result_json)
    except json.JSONDecodeError:
        return json.dumps({"error": "gate_result_json must be a valid JSON string"})

    result = al_analyze_risks(context, gate_result, company_name, process_area)
    return result.model_dump_json()


@mcp.tool()
def generate_allergen_management_xlsx(
    threats_json: str,
    company_name: str,
    process_area: str,
    evaluator_name: str,
    evaluation_date: str,
    materials_involved: str,
    gate_result_json: str
) -> str:
    """
    Genera el archivo XLSX con el formato oficial de Analisis de Riesgo
    de Gestion de Alergenos.
    """
    try:
        threats_raw = json.loads(threats_json)
        threats = [AllergenThreat(**t) for t in threats_raw]
        gate_result = json.loads(gate_result_json)
    except Exception as e:
        return json.dumps({"error": f"Error parsing inputs: {str(e)}"})

    result = export_allergen_management_xlsx(
        threats=threats,
        company_name=company_name,
        process_area=process_area,
        evaluator_name=evaluator_name,
        evaluation_date=evaluation_date,
        materials_involved=materials_involved,
        gate_result=gate_result,
        output_dir=OUTPUT_DIR
    )
    return result.model_dump_json()

# ── Health check (para Dokploy / Docker HEALTHCHECK) ─────────────────────
# FastMCP expone automáticamente GET / → 200 OK cuando usa transporte SSE.
# El Dockerfile hace HEALTHCHECK apuntando a /health; lo registramos aquí
# como resource MCP (no como endpoint HTTP separado, que no aplica en MCP puro).

@mcp.resource("vigia://health")
def health_resource() -> str:
    """Estado del servidor — usado por Dokploy para verificar disponibilidad."""
    return '{"status":"ok","service":"vigia-haccp-mcp","version":"1.0.0"}'


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info("=" * 60)
    logger.info("VIGÍA HACCP MCP  v1.0.0")
    logger.info("Transporte : SSE")
    logger.info("Endpoint   : http://%s:%d/sse", host, port)
    logger.info("Dokploy    : conectar la URL pública de tu servicio + /sse")
    logger.info("SurfSense  : Settings → MCP Servers → URL: https://<dominio>/sse")
    logger.info("=" * 60)
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="sse")
