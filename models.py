from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class StepType(str, Enum):
    receiving   = "receiving"
    storage     = "storage"
    preparation = "preparation"
    processing  = "processing"
    packaging   = "packaging"
    distribution = "distribution"


class TimeTemperatureProfile(BaseModel):
    temperature_celsius: float = 0.0
    duration_minutes:    Optional[float] = None
    target_unit:         Optional[str] = None   # e.g. "internal product"


class ProcessStep(BaseModel):
    step_number:            int
    step_name:              str
    step_type:              StepType
    time_temperature_profile: TimeTemperatureProfile = Field(
        default_factory=TimeTemperatureProfile
    )
    notes: Optional[str] = None


class HACCPRow(BaseModel):
    etapa:             str
    peligro:           str
    medida_preventiva: str
    es_pcc:            bool        # Para lógica interna (resaltado Excel, conteo PCCs)
    pcc_label:         str         # Texto display: "Sí" | "No (control por prerrequisitos)" | etc.
    limite_critico:    str
    monitoreo:         str
    accion_correctiva: str
    verificacion:      str
    registro:          str


class FDARecall(BaseModel):
    recall_number:      str
    product_description: str
    reason_for_recall:  str
    recalling_firm:     str
    recall_initiation_date: str
    classification:     str   # Class I / II / III
    status:             str
