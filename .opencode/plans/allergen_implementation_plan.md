# Plan de Implementación — Herramienta MCP de Gestión de Alérgenos

## Resumen
Agregar una nueva herramienta MCP para análisis de riesgo de gestión de alérgenos, siguiendo el mismo patrón que las herramientas existentes (Monitoreo Ambiental, Control de Plagas, Food Fraud). Incluye candado de validación de contexto (context gate), análisis de riesgos con matriz Food Fraud (Severidad I–IV × Ocurrencia A–E), y exportación a XLSX réplica del `alergenos.xlsx`.

---

## Archivos a modificar

### 1. `models.py` — Agregar al final (antes de EOF)

```python
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
```

### 2. `services/allergen_management_service.py` — Archivo nuevo

```python
import logging
from datetime import datetime

from models import AllergenContextValidation, AllergenThreat, AllergenAnalysisResult

logger = logging.getLogger("vigia.allergen_management_service")

# ── Matrix de Riesgo (Food Fraud) ──────────────────────────────────────────
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

# ── Context Validation ────────────────────────────────────────────────────

VALIDATION_CRITERIA = [
    {"id": "allergen_areas", "label": "Areas o procesos donde se manejan alergenos", "weight": 20, "critical": True,
     "signals": ["areas", "proceso", "almacen", "produccion", "envasado", "cocina", "recepcion", "linea"]},
    {"id": "allergen_types", "label": "Tipos de alergenos involucrados (leche, soya, huevo, etc.)", "weight": 25, "critical": True,
     "signals": ["alergeno", "leche", "soya", "huevo", "almendra", "nuez", "cacahuate", "gluten", "lactosa", "amarillo", "trigo", "soja", "allergen"]},
    {"id": "risk_description", "label": "Descripcion de riesgos de contacto cruzado", "weight": 20, "critical": True,
     "signals": ["riesgo", "contacto cruzado", "contaminacion", "derrames", "exposicion", "cruzada", "cruce"]},
    {"id": "current_controls", "label": "Controles actuales (PPRs, limpieza, etiquetado)", "weight": 20, "critical": False,
     "signals": ["controles", "limpieza", "etiquetado", "procedimientos", "ppr", "programa", "plan de manejo"]},
    {"id": "verification_methods", "label": "Metodos y frecuencia de verificacion", "weight": 15, "critical": False,
     "signals": ["verificacion", "frecuencia", "monitoreo", "inspeccion", "registros", "autoinspection"]},
]

def validate_context(available_context: str) -> AllergenContextValidation:
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
                "why": f"No se encontraron senales de: {criterion['label']}",
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
        xlsx_stamp = "Analisis verificado — contexto completo"
    elif score >= 40 and not critical_missing:
        gate = "PARTIAL"
        can_proceed = True
        xlsx_stamp = f"Analisis preliminar — score {score}/100"
        user_message = "El contexto es parcial. Faltan algunos elementos no criticos. Desea continuar?"
    else:
        gate = "BLOCKED"
        can_proceed = False
        user_message = "Analisis bloqueado. Falta informacion critica o el score es demasiado bajo."

    return AllergenContextValidation(
        gate=gate, score=score, present=present, missing=missing,
        critical_missing=critical_missing, user_message=user_message,
        xlsx_stamp=xlsx_stamp, can_proceed=can_proceed
    )

# ── Allergen Risk Patterns ────────────────────────────────────────────────

ALLERGEN_PATTERNS = [
    {
        "area": "Almacen de producto terminado",
        "keywords": ["almacen pt", "almacen", "producto terminado", "bodega", "rack", "estanteria"],
        "allergens": "Lactosa, Soya, Almendra, Colorante Amarillo 5, Gluten",
        "risk": "Derrames de leche por mal manejo de operadores que contaminan otros productos almacenados. Mal etiquetado. Desapego a la estructura definida de almacenaje. Pesado de alergenos. Mal armado de kits o batch para proceso.",
        "controls": "Plan de manejo de alergenos, procedimientos de limpieza por derrames, KIT para limpieza, diseno de practicas de almacenaje en RACKs (mismo alergeno encima o debajo).",
        "severity": "II",
        "occurrence": "B",
        "special": "NO. Los controles actuales demuestran consistencia.",
        "frequency": "Verificacion durante la operacion. Modo de accion de operadores. Registros. Auto inspecciones rutinarias."
    },
    {
        "area": "Recepcion de materias primas",
        "keywords": ["recepcion", "materias primas", "descarga", "proveedor", "ingreso de material"],
        "allergens": "Leche en polvo, Harina de trigo, Clara de huevo deshidratada, Leche entera, Crema de leche",
        "risk": "Ingreso de materias primas alergenicas sin identificacion clara. Riesgo de almacenamiento conjunto con no alergenicos. Proveedores sin declaracion de alergenos en etiquetas.",
        "controls": "Verificacion de etiquetado en recepcion. Checklist de materiales alergenicos. Zona de cuarentena para materiales no identificados.",
        "severity": "III",
        "occurrence": "C",
        "special": "SI. Reforzar verificacion de documentos de proveedores y etiquetado.",
        "frequency": "Cada recepcion. Muestreo aleatorio del 10% de los lotes recibidos."
    },
    {
        "area": "Area de produccion / proceso",
        "keywords": ["produccion", "proceso", "manufactura", "elaboracion", "mezclado", "coccion", "formado"],
        "allergens": "Leche liquida, Huevo entero, Harina de trigo, Soya texturizada, Suero de leche",
        "risk": "Contacto cruzado por aerosolizacion de alergenos en polvo. Limpieza ineficiente entre corridas de productos con diferente perfil alergenico. Re-trabajo de producto sin control de alergenos. Orden de produccion inadecuado.",
        "controls": "Programacion de produccion por sensibilidad alergenica (no alergenicos primero). Procedimientos de limpieza CIP intermedia. Pruebas de ATP y proteinas residuales. Utensilios codificados por color.",
        "severity": "I",
        "occurrence": "B",
        "special": "SI. Implementar verificacion con pruebas de ELISA o lateral flow post-limpieza.",
        "frequency": "Prueba de proteinas residuales despues de cada limpieza entre cambios de perfil alergenico."
    },
    {
        "area": "Area de envasado / empaque",
        "keywords": ["envasado", "empaque", "packaging", "linea de empaque", "sellado", "etiquetado"],
        "allergens": "Trazas de todos los alergenos de produccion",
        "risk": "Error de etiquetado (etiqueta incorrecta en producto equivocado). Contaminacion cruzada por aerosol en ambiente de envasado. Cambio de formato sin limpieza profunda de tolvas y conductos.",
        "controls": "Verificacion de etiquetas por codigo de barras. Procedimiento de cambio de formato con checklist. Aire comprimido filtrado. Diferencial de presion en sala de envasado.",
        "severity": "II",
        "occurrence": "B",
        "special": "SI. Implementar sistema de verificacion de etiquetas con scanner y doble chequeo.",
        "frequency": "Verificacion al inicio de cada corrida y cada cambio de SKU."
    },
    {
        "area": "Cocina / area de preparacion",
        "keywords": ["cocina", "preparacion", "coccion", "cocina caliente", "cocina fria", "kitchen"],
        "allergens": "Leche, Huevo, Trigo, Soya, Pescado, Cacahuate, Nuez, Almendra",
        "risk": "Uso de mismos utensilios para diferentes alergenos. Salpicaduras durante coccion. Almacenamiento de ingredientes sin tapa. Manipuladores sin conocimiento de alergenos. Contaminacion cruzada en planchas y freidoras.",
        "controls": "Utensilios y areas de preparacion separadas por alergeno. Freidoras designadas por tipo de alergeno. Capacitacion del personal. Etiquetado de contenedores en buffete.",
        "severity": "I",
        "occurrence": "C",
        "special": "SI. Implementar programa de capacitacion en alergenos para todo el personal de cocina.",
        "frequency": "Verificacion visual diaria. Auditoria semanal de buenas practicas."
    },
    {
        "area": "Limpieza de equipos (CIP / COP)",
        "keywords": ["limpieza", "cip", "cop", "sanitizacion", "lavado de equipos", "higiene"],
        "allergens": "Residuos de proteinas alergenicas en equipos",
        "risk": "Limpieza ineficiente que deja residuos de proteinas alergenicas. Diseno de equipo con espacios muertos. Tiempos de limpieza insuficientes. Concentracion de detergente inadecuada. Agua de enjuague contaminada.",
        "controls": "Validacion de limpieza con pruebas de proteinas. Parametros de CIP documentados (tiempo, temperatura, concentracion). Inspeccion visual post-limpieza.",
        "severity": "II",
        "occurrence": "C",
        "special": "SI. Establecer frecuencia de validacion de limpieza basada en nivel de riesgo del producto.",
        "frequency": "Prueba de proteinas residuales post-CIP en equipos de alto riesgo. Semanal en equipos de uso frecuente."
    },
    {
        "area": "Etiquetado y liberacion de producto",
        "keywords": ["etiquetado", "liberacion", "empaque final", "codigo de barras", "lote"],
        "allergens": "Declaracion de alergenos en empaque",
        "risk": "Etiqueta con declaracion de alergenos incorrecta o incompleta. Producto en empaque equivocado. Cambio de formulacion no reflejado en etiqueta. Lote sin trazabilidad alergenica.",
        "controls": "Sistema de gestion de etiquetas con control de versiones. Revision de arte por equipo de inocuidad. Prueba de alergenos en producto terminado para etiquetas "Puede contener".",
        "severity": "I",
        "occurrence": "B",
        "special": "SI. Implementar revision de etiquetas por equipo multidisciplinario antes de impresion.",
        "frequency": "Cada cambio de etiqueta o formulacion. Auditoria trimestral de etiquetado."
    }
]

def analyze_allergen_risks(
    context: str,
    gate_result: dict,
    company_name: str,
    process_area: str
) -> AllergenAnalysisResult:
    context_lower = context.lower()
    threats = []
    threat_id_counter = 1

    for pattern in ALLERGEN_PATTERNS:
        if any(kw in context_lower for kw in pattern["keywords"]):
            severity = pattern["severity"]
            occurrence = pattern["occurrence"]
            score = _RISK_MATRIX[severity][occurrence]

            res_sev_int = max(1, list(_SEVERITY_LABELS.keys()).index(severity))
            res_occ_int = max(1, list(_OCCURRENCE_LABELS.keys()).index(occurrence))
            res_sev_key = list(_SEVERITY_LABELS.keys())[res_sev_int - 1]
            res_occ_key = list(_OCCURRENCE_LABELS.keys())[res_occ_int - 1]
            res_score = _RISK_MATRIX[res_sev_key][res_occ_key]

            threats.append(AllergenThreat(
                id=f"AL{threat_id_counter:03d}",
                area=pattern["area"],
                allergens_involved=pattern["allergens"],
                risk_description=pattern["risk"],
                current_controls=pattern["controls"],
                severity=severity,
                severity_label=_SEVERITY_LABELS[severity],
                occurrence=occurrence,
                occurrence_label=_OCCURRENCE_LABELS[occurrence],
                risk_score=score,
                risk_level=get_risk_level(score),
                special_controls=pattern["special"],
                verification_frequency=pattern["frequency"],
                residual_severity=res_sev_key,
                residual_occurrence=res_occ_key,
                residual_risk_score=res_score,
                residual_risk_level=get_risk_level(res_score)
            ))
            threat_id_counter += 1

    high_priority_count = sum(1 for t in threats if t.risk_score <= 8)

    return AllergenAnalysisResult(
        threats=threats,
        total_threats=len(threats),
        high_priority_count=high_priority_count,
        analysis_metadata={
            "company_name": company_name,
            "process_area": process_area,
            "gate": gate_result.get("gate"),
            "score": gate_result.get("score"),
            "generated_at": datetime.now().isoformat()
        }
    )
```

### 3. `exporters/allergen_management_exporter.py` — Archivo nuevo

```python
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from models import AllergenThreat, AllergenExportResult

logger = logging.getLogger("vigia.allergen_management_exporter")

C_HEADER_BG = "95B3D7"
C_TITLE_BG = "FFFFFF"
C_WHITE = "FFFFFF"
C_BLACK = "000000"
C_BORDER = "000000"

C_RISK_EXTREME = "FF0000"
C_RISK_HIGH = "FF6600"
C_RISK_MEDIUM = "FFCC00"
C_RISK_LOW = "00CC00"

_thin = Border(
    left=Side(style="thin", color=C_BORDER),
    right=Side(style="thin", color=C_BORDER),
    top=Side(style="thin", color=C_BORDER),
    bottom=Side(style="thin", color=C_BORDER),
)
_wrap_center = Alignment(wrap_text=True, vertical="center", horizontal="center")
_wrap_top_left = Alignment(wrap_text=True, vertical="top", horizontal="left")


def _style(cell, value, bg=C_WHITE, bold=False, center=True, color=C_BLACK, size=10):
    cell.value = value
    cell.font = Font(name="Arial", bold=bold, size=size, color=color)
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.alignment = _wrap_center if center else _wrap_top_left
    cell.border = _thin


def _get_risk_bg(level: str):
    if level == "Extremely High": return C_RISK_EXTREME
    if level == "High": return C_RISK_HIGH
    if level == "Medium": return C_RISK_MEDIUM
    return C_RISK_LOW


def _get_risk_fg(level: str):
    if level in ("Extremely High", "High"): return C_WHITE
    return C_BLACK


def export_allergen_management_xlsx(
    threats: List[AllergenThreat],
    company_name: str,
    process_area: str,
    evaluator_name: str,
    evaluation_date: str,
    materials_involved: str,
    gate_result: dict,
    output_dir: Path
) -> AllergenExportResult:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Identificacion de servicios"

    # 1. Titulo
    ws.merge_cells("A1:J1")
    _style(ws["A1"], f"GRUPO DELCEN Analisis de Riesgo Gestion de alergenos - {company_name}", bg=C_TITLE_BG, bold=True, size=14, center=True)
    ws.row_dimensions[1].height = 30

    # 2. Proceso y fecha
    ws.merge_cells("A2:D2")
    _style(ws["A2"], f"Proceso: {process_area}", center=False, bold=True, size=11)
    ws.merge_cells("H2:J2")
    _style(ws["H2"], f"Fecha: {evaluation_date}", center=False, bold=True, size=11)

    # 3. Participantes y materiales
    ws.merge_cells("A3:D3")
    _style(ws["A3"], f"Participantes del equipo evaluador: {evaluator_name}", center=False, size=10)
    ws.merge_cells("H3:J3")
    _style(ws["H3"], f"Materiales y Productos involucrados: {materials_involved}", center=False, size=10)

    # 4. Encabezados (Fila 4 y 5)
    _style(ws.cell(row=4, column=1), "Area o Proceso", bg=C_HEADER_BG, bold=True, size=9, center=True)
    _style(ws.cell(row=4, column=2), "Alergenos involucrados: Describa el alergeno o la combinacion de los mismos. Describa la forma de los alergenos.", bg=C_HEADER_BG, bold=True, size=9, center=True)
    _style(ws.cell(row=4, column=3), "Descripcion de riesgos: Caracterizacion del riesgo. Como se puede presentar? Describa el impacto.", bg=C_HEADER_BG, bold=True, size=9, center=True)
    _style(ws.cell(row=4, column=4), "Controles Actuales: Ej. Metodos operacionales, programas de prerrequisitos, control sobre material de etiquetado, etc.", bg=C_HEADER_BG, bold=True, size=9, center=True)
    ws.merge_cells("E4:G4")
    _style(ws["E4"], "Evaluacion del Riesgo", bg=C_HEADER_BG, bold=True, size=9, center=True)
    _style(ws.cell(row=4, column=8), "Requiere medidas especiales de control? Mayor rigurosidad de ejecucion, supervision, cerrar frecuencias, mayor verificacion, inspecciones, etc. Describa", bg=C_HEADER_BG, bold=True, size=9, center=True)
    _style(ws.cell(row=4, column=9), "Establezca metodo y frecuencia de verificacion", bg=C_HEADER_BG, bold=True, size=9, center=True)
    _style(ws.cell(row=4, column=10), "Responsables y fechas", bg=C_HEADER_BG, bold=True, size=9, center=True)

    _style(ws.cell(row=5, column=5), "Sev.", bg=C_HEADER_BG, bold=True, size=9)
    _style(ws.cell(row=5, column=6), "Ocurr.", bg=C_HEADER_BG, bold=True, size=9)
    _style(ws.cell(row=5, column=7), "Nivel Riesgo", bg=C_HEADER_BG, bold=True, size=9)

    # 5. Filas de datos
    for ri, t in enumerate(threats, start=6):
        _style(ws.cell(row=ri, column=1), t.area, center=False)
        _style(ws.cell(row=ri, column=2), t.allergens_involved, center=False)
        _style(ws.cell(row=ri, column=3), t.risk_description, center=False)
        _style(ws.cell(row=ri, column=4), t.current_controls, center=False)

        _style(ws.cell(row=ri, column=5), t.severity)
        _style(ws.cell(row=ri, column=6), t.occurrence)
        risk_bg = _get_risk_bg(t.risk_level)
        risk_fg = _get_risk_fg(t.risk_level)
        _style(ws.cell(row=ri, column=7), t.risk_score, bg=risk_bg, bold=True, color=risk_fg)

        _style(ws.cell(row=ri, column=8), t.special_controls, center=False)
        _style(ws.cell(row=ri, column=9), t.verification_frequency, center=False)
        _style(ws.cell(row=ri, column=10), "")

        ws.row_dimensions[ri].height = 100

    # 6. Notas al pie
    last_data_row = 6 + len(threats)
    nr_row = last_data_row + 1
    ws.merge_cells(f"A{nr_row}:D{nr_row}")
    note1 = "NR (Nivel de riesgo): Resulta de multiplicar los indices de Severidad x Ocurrencia = NR. Las operaciones que hayan obtenido los mayores valores de NR seran los primeros en aplicar acciones recomendadas."
    _style(ws[f"A{nr_row}"], note1, center=False, size=9)

    ws.merge_cells(f"E{nr_row}:G{nr_row}")
    note2 = "Los criterios de evaluacion debe ser aprobada por el equipo de seguridad de los alimentos."
    _style(ws[f"E{nr_row}"], note2, center=False, size=9)

    ws.merge_cells(f"H{nr_row}:J{nr_row}")
    note3 = "Confirme que su matriz de Severidad y Ocurrencia define claramente los criterios."
    _style(ws[f"H{nr_row}"], note3, center=False, size=9)

    # Anchos de columna
    widths = [26, 24, 35, 32, 6, 7, 10, 32, 22, 18]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w

    # Hoja de criterios
    ws2 = wb.create_sheet("Criterios de evaluacion")
    ws2.merge_cells("B1:G1")
    _style(ws2["B1"], "MANEJO DE RIESGO OPERACIONAL: CRITERIOS DE EVALUACION DE RIESGOS", bg=C_TITLE_BG, bold=True, size=12)

    # Sello
    stamp_row = nr_row + 1
    ws.merge_cells(f"A{stamp_row}:J{stamp_row}")
    stamp_text = gate_result.get("xlsx_stamp", "Analisis generado por VIGIA Gestion de Alergenos")
    _style(ws[f"A{stamp_row}"], stamp_text, color="808080", size=10, center=True)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = "".join(c if c.isalnum() else "_" for c in company_name)[:20]
    safe_area = "".join(c if c.isalnum() else "_" for c in process_area)[:20]
    file_name = f"alergenos_{safe_company}_{safe_area}_{timestamp}.xlsx"
    file_path = output_dir / file_name
    wb.save(file_path)

    high_priority_rows = sum(1 for t in threats if t.risk_score <= 8)

    return AllergenExportResult(
        file_path=str(file_path),
        file_name=file_name,
        download_url=f"/outputs/{file_name}",
        total_rows=len(threats),
        high_priority_rows=high_priority_rows
    )
```

### 4. `server.py` — Agregar imports y tools

**Imports** (agregar junto a los otros imports de environmental/pest):
```python
from services.allergen_management_service import (
    validate_context as al_validate_context,
    analyze_allergen_risks as al_analyze_risks
)
from exporters.allergen_management_exporter import export_allergen_management_xlsx
```

**Models import** (agregar `AllergenThreat` a la línea existente):
```python
from models import (
    ..., AllergenThreat
)
```

**Tools** (agregar antes de `# ── Health check`):
```python
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
```

---

## Matriz de riesgo (Food Fraud)

| Severidad \ Ocurrencia | A (Frequent) | B (Likely) | C (Occasional) | D (Seldom) | E (Unlikely) |
|---|---|---|---|---|---|
| **I (Catastrophic)** | 1 (Extremely High) | 2 (Extremely High) | 6 (High) | 8 (High) | 12 (Medium) |
| **II (Critical)** | 3 (Extremely High) | 4 (Extremely High) | 7 (High) | 11 (Medium) | 15 (Low) |
| **III (Moderate)** | 5 (High) | 9 (Medium) | 10 (Medium) | 14 (Medium) | 16 (Low) |
| **IV (Negligible)** | 13 (Low) | 17 (Low) | 18 (Low) | 19 (Low) | 20 (Low) |

---

## Context Gate — Criterios de validación

| ID | Requisito | Peso | Crítico |
|---|---|---|---|
| `allergen_areas` | Áreas o procesos donde se manejan alérgenos | 20 | Sí |
| `allergen_types` | Tipos de alérgenos involucrados | 25 | Sí |
| `risk_description` | Descripción de riesgos de contacto cruzado | 20 | Sí |
| `current_controls` | Controles actuales (PPRs, limpieza, etiquetado) | 20 | No |
| `verification_methods` | Métodos y frecuencia de verificación | 15 | No |

Niveles: `OPEN` (≥75 sin críticos faltantes) → `PARTIAL` (≥40 sin críticos faltantes) → `BLOCKED`

---

## Áreas analizadas (7 patrones)

1. Almacén de producto terminado
2. Recepción de materias primas
3. Área de producción / proceso
4. Área de envasado / empaque
5. Cocina / área de preparación
6. Limpieza de equipos (CIP / COP)
7. Etiquetado y liberación de producto

---

## Estructura del XLSX generado

**Hoja 1: "Identificación de servicios"** (A–J):
| Col | Header |
|-----|--------|
| A | Area o Proceso |
| B | Alérgenos involucrados |
| C | Descripción de riesgos |
| D | Controles Actuales |
| E | Sev. (I–IV) |
| F | Ocurr. (A–E) |
| G | Nivel Riesgo (1–20) |
| H | Medidas especiales de control |
| I | Método y frecuencia de verificación |
| J | Responsables y fechas |

**Hoja 2: "Criterios de evaluación"** — Título de criterios

---

## Instrucciones de aplicación

1. Agregar los modelos al final de `models.py` (antes de EOF)
2. Crear `services/allergen_management_service.py` con el contenido completo
3. Crear `exporters/allergen_management_exporter.py` con el contenido completo
4. En `server.py`:
   - Agregar los imports de allergen_management_service y exporter
   - Agregar `AllergenThreat` al import de models
   - Agregar las 3 tools antes del health check
5. Verificar con: `python3 -c "import py_compile; py_compile.compile('server.py', doraise=True); print('OK')"`
6. Ejecutar ejemplo de prueba
