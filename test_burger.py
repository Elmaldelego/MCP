import json
import asyncio
from services.food_fraud_service import validate_context, get_fraud_reference_data, analyze_fraud_threats
from exporters.food_fraud_exporter import export_food_fraud_xlsx
from pathlib import Path

# Contexto para una planta de hamburguesas
BURGER_CONTEXT = """
Proceso: Recepción de carne de res en canal y block congelado, molienda, formado de medallones de hamburguesa, congelación rápida y empaque.
Ingredientes: Carne de res 80/20 proveniente de rastros locales y proveedores en EE.UU.
Controles: Verificación de temperatura de transporte, inspección de etiquetas y certificados sanitarios.
Criterios: Matriz de severidad y ocurrencia basada en estándares FSMA.
Historial: No se han reportado adulteraciones en este sitio en los últimos 2 años.
"""

async def run_burger_test():
    print("--- 1. Validando Contexto (Hamburguesas) ---")
    gate_result = validate_context(BURGER_CONTEXT)
    print(f"Gate: {gate_result.gate}, Score: {gate_result.score}/100")
    
    print("\n--- 2. Análisis de Amenazas de Fraude ---")
    analysis = analyze_fraud_threats(
        context=BURGER_CONTEXT,
        gate_result=gate_result.model_dump(),
        company_name="Burger Master Pro",
        process_area="Línea de Formado"
    )
    
    for t in analysis.threats:
        print(f"Amenaza: {t.threat_description}")
        print(f"Riesgo: {t.risk_level} ({t.risk_score})")
        print(f"Mitigaciones Sugeridas:\n{t.mitigation_proposals}\n")

    print("--- 3. Generando Excel ---")
    output_dir = Path("outputs")
    export_result = export_food_fraud_xlsx(
        threats=analysis.threats,
        company_name="Burger Master Pro",
        process_area="Línea de Formado",
        evaluator_name="VIGÍA Agent",
        evaluation_date="20/05/2026",
        gate_result=gate_result.model_dump(),
        analysis_metadata=analysis.analysis_metadata.model_dump(),
        output_dir=output_dir
    )
    print(f"Archivo listo: {export_result.file_name}")

if __name__ == "__main__":
    asyncio.run(run_burger_test())
