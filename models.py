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


class CAERSEvent(BaseModel):
    report_number: str
    date_created: str
    outcomes: list[str]
    reactions: list[str]
    product_names: list[str]
    industry_name: Optional[str] = None


# ── Food Fraud Models ─────────────────────────────────────────────────────

class ContextRequirement(BaseModel):
    id: str
    label: str
    why: str
    critical: bool


class ContextValidation(BaseModel):
    gate: str  # "OPEN" | "PARTIAL" | "BLOCKED"
    score: int
    present: list[str]
    missing: list[dict]
    critical_missing: bool
    user_message: Optional[str] = None
    xlsx_stamp: Optional[str] = None
    can_proceed: bool


class FraudThreat(BaseModel):
    id: str
    threat_description: str
    potential_effect: str
    potential_causes: list[str]
    severity: str
    severity_label: str
    occurrence: str
    occurrence_label: str
    risk_score: int
    risk_level: str
    current_controls: str
    mitigation_proposals: str
    data_confidence: str
    uncertain: bool


class FraudAnalysisMetadata(BaseModel):
    gate: str
    score: int
    generated_at: str


class FraudAnalysisResult(BaseModel):
    threats: list[FraudThreat]
    total_threats: int
    high_priority_count: int
    analysis_metadata: FraudAnalysisMetadata


class FraudMethod(BaseModel):
    method: str
    adulterant: str
    frequency: str
    detection: str
    references: list[str]


class FraudReferenceData(BaseModel):
    ingredient: str
    known_fraud_methods: list[FraudMethod]
    vulnerability_index: str
    price_volatility: str
    paperless_docs: Optional[list[dict]] = None


class FoodFraudExportResult(BaseModel):
    file_path: str
    file_name: str
    download_url: str
    total_rows: int
    high_priority_rows: int
    stamp_applied: str


# ── Food Defense Models ───────────────────────────────────────────────────

class DefenseThreat(BaseModel):
    id: str
    threat_description: str
    potential_effect: str
    potential_causes: list[str]
    severity: int        # 1-4
    occurrence: int      # 1-3 (Total risk 1-12)
    risk_score: int      # Sev * Ocurr
    risk_level: str      # Low / Medium / High
    current_controls: str
    mitigation_proposals: str
    residual_severity: int
    residual_occurrence: int
    residual_risk_score: int
    residual_risk_level: str
    uncertain: bool


class FoodDefenseAnalysisResult(BaseModel):
    threats: list[DefenseThreat]
    total_threats: int
    high_priority_count: int
    analysis_metadata: dict


class FoodDefenseExportResult(BaseModel):
    file_path: str
    file_name: str
    download_url: str
    total_rows: int
    high_priority_rows: int


# ── Environmental Monitoring Models ─────────────────────────────────────────

class EnvironmentalContextValidation(BaseModel):
    gate: str
    score: int
    present: list[str]
    missing: list[dict]
    critical_missing: bool
    user_message: Optional[str] = None
    xlsx_stamp: Optional[str] = None
    can_proceed: bool


class EnvironmentalThreat(BaseModel):
    id: str
    area: str
    area_category: str
    microbiological_risk: str
    risk_activators: str
    sanitation_abilities: str
    severity: int
    occurrence: int
    risk_score: int
    risk_level: str
    special_controls: str
    verification_frequency: str
    residual_severity: int
    residual_occurrence: int
    residual_risk_score: int
    residual_risk_level: str


class EnvironmentalAnalysisResult(BaseModel):
    threats: list[EnvironmentalThreat]
    total_threats: int
    high_priority_count: int
    analysis_metadata: dict


class EnvironmentalExportResult(BaseModel):
    file_path: str
    file_name: str
    download_url: str
    total_rows: int
    high_priority_rows: int


# ── Pest Management (MIP) Models ─────────────────────────────────────────────

class PestContextValidation(BaseModel):
    gate: str
    score: int
    present: list[str]
    missing: list[dict]
    critical_missing: bool
    user_message: Optional[str] = None
    xlsx_stamp: Optional[str] = None
    can_proceed: bool


class PestThreat(BaseModel):
    id: str
    area: str
    pest_risk: str
    potential_causes: str
    strategic_approach: str
    operational_approach: str
    severity: int
    occurrence: int
    risk_score: int
    risk_level: str
    acceptable_threshold: str
    plant_actions: str
    supplier_actions: str
    residual_severity: int
    residual_occurrence: int
    residual_risk_score: int
    residual_risk_level: str


class PestAnalysisResult(BaseModel):
    threats: list[PestThreat]
    total_threats: int
    high_priority_count: int
    analysis_metadata: dict


class PestExportResult(BaseModel):
    file_path: str
    file_name: str
    download_url: str
    total_rows: int
    high_priority_rows: int


# ── Allergen Management Models ──────────────────────────────────────────────

class AllergenContextValidation(BaseModel):
    gate: str
    score: int
    present: list[str]
    missing: list[dict]
    critical_missing: bool
    user_message: Optional[str] = None
    xlsx_stamp: Optional[str] = None
    can_proceed: bool


class AllergenThreat(BaseModel):
    id: str
    area: str
    allergens_involved: str
    risk_description: str
    current_controls: str
    severity: str
    severity_label: str
    occurrence: str
    occurrence_label: str
    risk_score: int
    risk_level: str
    special_controls: str
    verification_frequency: str
    residual_severity: str
    residual_occurrence: str
    residual_risk_score: int
    residual_risk_level: str


class AllergenAnalysisResult(BaseModel):
    threats: list[AllergenThreat]
    total_threats: int
    high_priority_count: int
    analysis_metadata: dict


class AllergenExportResult(BaseModel):
    file_path: str
    file_name: str
    download_url: str
    total_rows: int
    high_priority_rows: int