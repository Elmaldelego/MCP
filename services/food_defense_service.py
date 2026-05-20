import json
import logging
from datetime import datetime
from typing import List, Dict

from models import DefenseThreat, FoodDefenseAnalysisResult

logger = logging.getLogger("vigia.food_defense_service")

# ── Risk Matrix (Food Defense MRO) ────────────────────────────────────────
# Severity (1-4) x Occurrence (1-3)
# Total Risk = Severity * Occurrence (1-12)

def get_defense_risk_level(score: int) -> str:
    if score >= 9: return "High"
    if score >= 4: return "Medium"
    return "Low"

# ── Threat Patterns ───────────────────────────────────────────────────────

DEFENSE_PATTERNS = [
    {
        "area": "recepción",
        "keywords": ["recepción", "muelle", "descarga", "entrada", "receiving"],
        "threats": [
            {
                "description": "Ingreso de personal no autorizado a muelle de descarga",
                "effect": "Contaminación intencional de materias primas",
                "causes": ["Falta de control de accesos", "Supervisión insuficiente de transportistas"],
                "severity": 4,
                "occurrence": 2,
                "mitigations": ["Control de acceso biométrico", "Registro obligatorio de transportistas", "CCTV en muelle"]
            }
        ]
    },
    {
        "area": "procesamiento",
        "keywords": ["molienda", "mezclado", "formado", "cocción", "processing"],
        "threats": [
            {
                "description": "Sabotaje en equipo de proceso (molienda/mezclado)",
                "effect": "Daño a la marca y riesgo masivo a la salud",
                "causes": ["Personal descontento", "Acceso libre a áreas críticas"],
                "severity": 4,
                "occurrence": 1,
                "mitigations": ["Criterios de contratación rigurosos", "Supervisión cercana", "Restricción de objetos personales"]
            }
        ]
    },
    {
        "area": "almacenamiento",
        "keywords": ["almacén", "cámara", "congelado", "storage"],
        "threats": [
            {
                "description": "Contaminación intencional de producto terminado",
                "effect": "Retiro del mercado y pérdida de confianza",
                "causes": ["Almacén sin llave/candado", "Iluminación deficiente"],
                "severity": 3,
                "occurrence": 1,
                "mitigations": ["Control de llaves", "Sensores de movimiento", "Inspección diaria de integridad"]
            }
        ]
    },
    {
        "area": "servicios",
        "keywords": ["agua", "químicos", "cisterna", "planta de luz"],
        "threats": [
            {
                "description": "Manipulación de sistema de agua o suministro eléctrico",
                "effect": "Paro de planta o contaminación sistémica",
                "causes": ["Exposición externa de infraestructura", "Falta de cercado perimetral"],
                "severity": 4,
                "occurrence": 1,
                "mitigations": ["Cercado perimetral con concertina", "Cerraduras de seguridad en cisternas", "Iluminación perimetral"]
            }
        ]
    }
]

def analyze_food_defense(
    context: str,
    company_name: str,
    process_area: str
) -> FoodDefenseAnalysisResult:
    context_lower = context.lower()
    threats = []
    threat_id_counter = 1

    for pattern in DEFENSE_PATTERNS:
        if any(kw in context_lower for kw in pattern["keywords"]):
            for t_data in pattern["threats"]:
                severity = t_data["severity"]
                occurrence = t_data["occurrence"]
                score = severity * occurrence
                
                # Residual risk calculation (simplified simulation)
                res_sev = severity
                res_occ = max(1, occurrence - 1)
                res_score = res_sev * res_occ

                threats.append(DefenseThreat(
                    id=f"FD{threat_id_counter:03d}",
                    threat_description=t_data["description"],
                    potential_effect=t_data["effect"],
                    potential_causes=t_data["causes"],
                    severity=severity,
                    occurrence=occurrence,
                    risk_score=score,
                    risk_level=get_defense_risk_level(score),
                    current_controls="Controles básicos de planta",
                    mitigation_proposals="\n".join(f"• {m}" for m in t_data["mitigations"]),
                    residual_severity=res_sev,
                    residual_occurrence=res_occ,
                    residual_risk_score=res_score,
                    residual_risk_level=get_defense_risk_level(res_score),
                    uncertain=False
                ))
                threat_id_counter += 1

    high_priority_count = sum(1 for t in threats if t.risk_score >= 9)

    return FoodDefenseAnalysisResult(
        threats=threats,
        total_threats=len(threats),
        high_priority_count=high_priority_count,
        analysis_metadata={
            "company_name": company_name,
            "process_area": process_area,
            "generated_at": datetime.now().isoformat()
        }
    )
