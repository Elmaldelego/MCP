import json
import asyncio
from services.food_defense_service import analyze_food_defense
from exporters.food_defense_exporter import export_food_defense_xlsx
from pathlib import Path

# Contexto para Food Defense en planta de hamburguesas
DEFENSE_CONTEXT = """
Área de muelle: Cuenta con 3 rampas de descarga, acceso directo desde calle principal.
Proceso: Molienda de carne, mezclado de especias, formado y empaque.
Instalaciones: Cisterna de agua potable en patio trasero, almacén de químicos de limpieza.
Seguridad actual: Vigilante en puerta principal, cámaras generales.
"""

async def run_defense_example():
    print("--- 1. Analizando Amenazas Food Defense (MRO) ---")
    analysis = analyze_food_defense(
        context=DEFENSE_CONTEXT,
        company_name="Burger Master Pro",
        process_area="Planta Completa"
    )
    
    print(f"Total amenazas identificadas: {analysis.total_threats}")
    for t in analysis.threats:
        print(f"\nAmenaza: {t.threat_description}")
        print(f"Riesgo Inicial: {t.risk_level} ({t.risk_score})")
        print(f"Riesgo Residual: {t.residual_risk_level} ({t.residual_risk_score})")
        print(f"Mitigaciones:\n{t.mitigation_proposals}")

    print("\n--- 2. Generando Reporte Excel (Formato Delcen MRO) ---")
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    export_result = export_food_defense_xlsx(
        threats=analysis.threats,
        company_name="Burger Master Pro",
        process_area="Planta Completa",
        output_dir=output_dir
    )
    print(f"Excel generado: {export_result.file_name}")
    print(f"Ruta: {export_result.file_path}")

if __name__ == "__main__":
    asyncio.run(run_defense_example())
