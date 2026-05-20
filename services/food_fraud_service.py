import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import (
    ContextValidation, FraudThreat, FraudAnalysisResult, 
    FraudReferenceData, FraudMethod, FraudAnalysisMetadata
)

logger = logging.getLogger("vigia.food_fraud_service")

FRAUD_DB_PATH = Path(os.getenv("FRAUD_DB_PATH", "data/fraud_database.json"))

# ── Matrix de Riesgo ──────────────────────────────────────────────────────
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

# ── Context Validation Logic ──────────────────────────────────────────────

VALIDATION_CRITERIA = [
    {"id": "process_flow", "label": "Diagrama de flujo o descripción del proceso", "weight": 20, "critical": True, 
     "signals": ["diagrama de flujo", "proceso", "etapas", "recepción", "almacenamiento", "envasado", "flowchart", "process flow"]},
    {"id": "raw_materials", "label": "Lista de materias primas con origen y proveedor", "weight": 30, "critical": True, 
     "signals": ["materias primas", "ingredientes", "proveedor", "origen", "lista de materiales", "raw materials", "supplier"]},
    {"id": "current_controls", "label": "Controles actuales documentados", "weight": 20, "critical": False, 
     "signals": ["controles", "monitoreo", "verificación", "pcc", "puntos de control", "inspección", "controls", "monitoring"]},
    {"id": "fraud_history", "label": "Base de adulteraciones conocidas", "weight": 15, "critical": False, 
     "signals": ["historial", "fraudes previos", "alertas", "rasff", "adulteraciones", "fraud history", "known fraud"]},
    {"id": "risk_criteria", "label": "Criterios de severidad y ocurrencia (GFSI/FSMA)", "weight": 15, "critical": False, 
     "signals": ["criterios de riesgo", "severidad", "ocurrencia", "matriz de riesgo", "gfsi", "fsma", "risk criteria", "severity", "occurrence"]},
]

def validate_context(available_context: str) -> ContextValidation:
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
                "why": f"No se encontraron señales de {criterion['label']}",
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
        xlsx_stamp = "✅ Análisis verificado — contexto completo"
    elif score >= 40 and not critical_missing:
        gate = "PARTIAL"
        can_proceed = True
        xlsx_stamp = f"⚠️ Análisis preliminar — score {score}/100"
        user_message = "El contexto es parcial. Faltan algunos elementos no críticos. ¿Desea continuar?"
    else:
        gate = "BLOCKED"
        can_proceed = False
        user_message = "Análisis bloqueado. Falta información crítica o el score es demasiado bajo."

    return ContextValidation(
        gate=gate,
        score=score,
        present=present,
        missing=missing,
        critical_missing=critical_missing,
        user_message=user_message,
        xlsx_stamp=xlsx_stamp,
        can_proceed=can_proceed
    )

# ── Reference Data Logic ──────────────────────────────────────────────────

def get_fraud_reference_data(ingredient: str) -> FraudReferenceData:
    if not FRAUD_DB_PATH.exists():
        logger.error(f"Fraud database not found at {FRAUD_DB_PATH}")
        return FraudReferenceData(
            ingredient=ingredient,
            known_fraud_methods=[],
            vulnerability_index="unknown",
            price_volatility="unknown"
        )

    with open(FRAUD_DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)

    # Simple matching
    ingredient_key = ingredient.lower().replace(" ", "_")
    data = db.get("ingredients", {}).get(ingredient_key)

    if not data:
        # Try partial match
        for key, val in db.get("ingredients", {}).items():
            if key in ingredient_key or ingredient_key in key:
                data = val
                break

    if not data:
        return FraudReferenceData(
            ingredient=ingredient,
            known_fraud_methods=[],
            vulnerability_index="medium",
            price_volatility="medium"
        )

    return FraudReferenceData(
        ingredient=ingredient,
        known_fraud_methods=[FraudMethod(**m) for m in data["known_fraud_methods"]],
        vulnerability_index=data["vulnerability_index"],
        price_volatility=data["price_volatility"]
    )

# ── Threat Analysis Logic ─────────────────────────────────────────────────

def analyze_fraud_threats(
    context: str,
    gate_result: dict,
    company_name: str,
    process_area: str
) -> FraudAnalysisResult:
    # This implementation is a bit more than a keyword search, it tries to identify
    # ingredients from our DB in the context and generate threats for them.
    
    context_lower = context.lower()
    threats = []
    
    if not FRAUD_DB_PATH.exists():
        return FraudAnalysisResult(
            threats=[],
            total_threats=0,
            high_priority_count=0,
            analysis_metadata=FraudAnalysisMetadata(
                gate=gate_result["gate"],
                score=gate_result["score"],
                generated_at=datetime.now().isoformat()
            )
        )

    with open(FRAUD_DB_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)

    threat_id_counter = 1
    
    for ing_name, ing_data in db.get("ingredients", {}).items():
        # Check if ingredient is mentioned in context
        if ing_name.replace("_", " ") in context_lower:
            for method in ing_data["known_fraud_methods"]:
                # Determine severity and occurrence based on DB and gate
                # Default logic for this tool implementation
                severity = "II" if ing_data["vulnerability_index"] == "high" else "III"
                occurrence = "B" if method["frequency"] == "common" else "C"
                
                score = _RISK_MATRIX[severity][occurrence]
                
                # Mitigation proposals logic
                proposals = [
                    "Mejora de los criterios de evaluación de los proveedores (auditorías de segunda parte)",
                    f"Análisis de autenticidad para {ing_name.replace('_', ' ')}: {method['detection']}"
                ]
                if ing_data["vulnerability_index"] == "high":
                    proposals.append("Restricción a proveedores certificados (ej. GFSI, BRC, IFS)")
                if score <= 8:
                    proposals.append("Implementar balance de masas y trazabilidad granular por lote")

                threats.append(FraudThreat(
                    id=f"T{threat_id_counter:03d}",
                    threat_description=f"Fraude por {method['method']} en {ing_name.replace('_', ' ')}",
                    potential_effect=f"Impacto en la autenticidad del producto y posible riesgo para la salud por {method['adulterant']}",
                    potential_causes=[f"Presión económica por {ing_data['price_volatility']} volatilidad de precios", "Falta de controles de autenticidad en origen"],
                    severity=severity,
                    severity_label=_SEVERITY_LABELS[severity],
                    occurrence=occurrence,
                    occurrence_label=_OCCURRENCE_LABELS[occurrence],
                    risk_score=score,
                    risk_level=get_risk_level(score),
                    current_controls="No especificados en contexto detallado" if "controles" not in context_lower else "Controles generales de recepción",
                    mitigation_proposals="\n".join(f"• {p}" for p in proposals),
                    data_confidence="high" if gate_result["score"] >= 75 else "medium",
                    uncertain=gate_result["gate"] == "PARTIAL"
                ))
                threat_id_counter += 1

    high_priority_count = sum(1 for t in threats if t.risk_score <= 8)

    return FraudAnalysisResult(
        threats=threats,
        total_threats=len(threats),
        high_priority_count=high_priority_count,
        analysis_metadata=FraudAnalysisMetadata(
            gate=gate_result["gate"],
            score=gate_result["score"],
            generated_at=datetime.now().isoformat()
        )
    )
