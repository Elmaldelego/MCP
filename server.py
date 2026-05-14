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

from models import ProcessStep, TimeTemperatureProfile, StepType
from services.openfda import OpenFDAClient
from services.haccp_generator import extract_fda_hazards, generate_haccp_rows
from exporters.excel_exporter import export_to_excel

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
    description=(
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
async def search_fda_recalls(
    product_name: str,
    hazard_types: str = "",
) -> str:
    """
    Busca retiros de mercado reales en la base de datos de la FDA (últimos 5 años)
    para el producto o ingrediente especificado.

    Úsala cuando el usuario quiera:
    - Conocer el historial de retiros de un producto o ingrediente específico
    - Identificar qué peligros han causado retiros reales en la industria
    - Enriquecer un análisis de riesgos con evidencia real antes de generar el HACCP

    Args:
        product_name:  Nombre del producto o ingrediente (ej: "beef", "cheese", "salami").
                       Usa términos en inglés para mejores resultados en openFDA.
        hazard_types:  Peligros a buscar separados por coma
                       (ej: "Listeria, Salmonella, allergen").
                       Dejar vacío para buscar solo por producto.

    Retorna: JSON con lista de retiros encontrados y resumen de peligros identificados.
    """
    fda = OpenFDAClient()
    areas = [h.strip() for h in hazard_types.split(",") if h.strip()]

    try:
        recalls = await fda.fetch_all(product_name, areas, limit_per_query=10)
    except Exception as exc:
        logger.error("Error consultando openFDA: %s", exc)
        return json.dumps({"error": str(exc), "recalls": []}, ensure_ascii=False)

    hazards = extract_fda_hazards(recalls)

    result = {
        "total_recalls_found": len(recalls),
        "fda_hazards_detected": sorted(hazards),
        "recalls": [
            {
                "recall_number":   r.recall_number,
                "firm":            r.recalling_firm,
                "product":         r.product_description[:200],
                "reason":          r.reason_for_recall[:200],
                "date":            r.recall_initiation_date,
                "classification":  r.classification,
            }
            for r in recalls[:20]
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
        recalls = await fda_client.fetch_all(fda_keyword, areas, limit_per_query=10)
    except Exception as exc:
        logger.warning("openFDA falló, continuando sin datos FDA: %s", exc)
        recalls = []

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
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


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
    mcp.run(transport="sse", host=host, port=port)
