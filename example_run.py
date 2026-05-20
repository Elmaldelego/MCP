import json
import asyncio
from services.food_fraud_service import validate_context, get_fraud_reference_data, analyze_fraud_threats
from exporters.food_fraud_exporter import export_food_fraud_xlsx
from pathlib import Path
import os

# Mock context for "Mieles del Sur S.A."
SAMPLE_CONTEXT = """
Diagrama de flujo: Recepción de miel en tambores, filtrado, calentamiento controlado a 45C, envasado y etiquetado.
Materias primas: Miel multiflora de proveedores locales en Yucatán (Apiarios Unidos).
Controles: Se revisa certificado de origen y se realiza inspección visual en recepción.
Criterios: Seguimos lineamientos GFSI para evaluación de riesgos.
"""

async def run_example():
    print("--- 1. Validando Contexto ---")
    gate_result = validate_context(SAMPLE_CONTEXT)
    print(f"Gate: {gate_result.gate}, Score: {gate_result.score}")
    print(f"Stamp: {gate_result.xlsx_stamp}")
    
    print("\n--- 2. Obteniendo Datos de Referencia (Miel) ---")
    ref_data = get_fraud_reference_data("miel")
    print(f"Vulnerabilidad: {ref_data.vulnerability_index}")
    for m in ref_data.known_fraud_methods:
        print(f" - Método: {m.method}")

    print("\n--- 3. Analizando Amenazas ---")
    analysis = analyze_fraud_threats(
        context=SAMPLE_CONTEXT,
        gate_result=gate_result.model_dump(),
        company_name="Mieles del Sur S.A.",
        process_area="Planta de Envasado"
    )
    print(f"Total amenazas encontradas: {analysis.total_threats}")
    for t in analysis.threats:
        print(f" - [{t.id}] {t.threat_description} | Riesgo: {t.risk_level} ({t.risk_score})")

    print("\n--- 4. Generando Reporte Excel ---")
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    export_result = export_food_fraud_xlsx(
        threats=analysis.threats,
        company_name="Mieles del Sur S.A.",
        process_area="Planta de Envasado",
        evaluator_name="Gemini CLI Agent",
        evaluation_date="20/05/2026",
        gate_result=gate_result.model_dump(),
        analysis_metadata=analysis.analysis_metadata.model_dump(),
        output_dir=output_dir
    )
    print(f"Excel generado: {export_result.file_name}")
    print(f"Ruta: {export_result.file_path}")

if __name__ == "__main__":
    asyncio.run(run_example())
