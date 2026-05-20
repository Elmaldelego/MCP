# MCP — Evaluación de Riesgos de Monitoreo Ambiental Microbiológico

## Especificación técnica de implementación

---

## 1. Propósito

Servidor MCP que automatiza la evaluación de riesgos de monitoreo ambiental microbiológico. Dado un contexto de documentos del cliente (descripción de áreas, procesos, medidas de saneamiento), el servidor valida que la información mínima esté presente, ejecuta el análisis de riesgos microbiológicos por área y genera el formato oficial en XLSX basado en la plantilla `ambiental.xlsx`.

---

## 2. Stack tecnológico

| Componente | Tecnología |
|---|---|
| Framework MCP | `fastmcp` (Python) |
| Transporte | SSE (mismo servidor VIGÍA HACCP) |
| Generación XLSX | `openpyxl` |
| Entorno | Python 3.11+, Docker-compatible |

---

## 3. Estructura de archivos modificados/creados

```
vigia-haccp-mcp/
├── models.py                                                # + Modelos EnvironmentalMonitoring
├── services/
│   └── environmental_monitoring_service.py   [CREADO]       # Lógica de validación + análisis
├── exporters/
│   └── environmental_monitoring_exporter.py  [CREADO]       # Generación de XLSX
├── server.py                                                # + 3 nuevas tools MCP
├── ambiental.xlsx                                           # Plantilla de referencia (sin cambios)
└── environmental-mcp-spec.md                  [CREADO]       # Este documento
```

---

## 4. Models agregados a `models.py`

### `EnvironmentalContextValidation`
Valida el resultado del context gate (candado de validación), idéntico en estructura al `ContextValidation` de Food Fraud.

| Campo | Tipo | Descripción |
|---|---|---|
| `gate` | `str` | `OPEN`, `PARTIAL` o `BLOCKED` |
| `score` | `int` | Puntaje 0–100 |
| `present` | `list[str]` | IDs de requisitos encontrados |
| `missing` | `list[dict]` | Requisitos faltantes con id, label, why, critical |
| `critical_missing` | `bool` | Si falta algún requisito crítico |
| `user_message` | `Optional[str]` | Mensaje para mostrar al usuario |
| `xlsx_stamp` | `Optional[str]` | Sello que se imprime en el XLSX |
| `can_proceed` | `bool` | Si se puede continuar con el análisis |

### `EnvironmentalThreat`
Representa una amenaza/riesgo identificado por área de proceso.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `str` | Identificador único (EM001, EM002...) |
| `area` | `str` | Nombre del área o proceso |
| `area_category` | `str` | Categorización (Alta/Media/Baja criticidad) |
| `microbiological_risk` | `str` | Riesgos microbiológicos identificados |
| `risk_activators` | `str` | Qué activa el riesgo |
| `sanitation_abilities` | `str` | Habilidades de limpieza/saneamiento |
| `severity` | `int` | Severidad (1–4) |
| `occurrence` | `int` | Ocurrencia (1–3) |
| `risk_score` | `int` | Severidad × Ocurrencia (1–12) |
| `risk_level` | `str` | High / Medium / Low |
| `special_controls` | `str` | Medidas especiales de control |
| `verification_frequency` | `str` | Frecuencia de verificación |
| `residual_severity` | `int` | Severidad residual esperada |
| `residual_occurrence` | `int` | Ocurrencia residual esperada |
| `residual_risk_score` | `int` | Riesgo residual |
| `residual_risk_level` | `str` | Nivel de riesgo residual |

### `EnvironmentalAnalysisResult`
Resultado completo del análisis.

| Campo | Tipo | Descripción |
|---|---|---|
| `threats` | `list[EnvironmentalThreat]` | Lista de amenazas identificadas |
| `total_threats` | `int` | Total de amenazas |
| `high_priority_count` | `int` | Amenazas con riesgo ≥ 9 |
| `analysis_metadata` | `dict` | Metadatos (empresa, área, fecha) |

### `EnvironmentalExportResult`
Resultado de la exportación a XLSX.

| Campo | Tipo | Descripción |
|---|---|---|
| `file_path` | `str` | Ruta absoluta del archivo |
| `file_name` | `str` | Nombre del archivo |
| `download_url` | `str` | URL de descarga |
| `total_rows` | `int` | Filas totales |
| `high_priority_rows` | `int` | Filas de alta prioridad |

---

## 5. Tools del MCP

### 5.1 `validate_environmental_context`

**Context Gate (candado de validación) obligatorio.** Debe llamarse siempre antes de cualquier análisis de monitoreo ambiental.

Evalúa si el contexto cubre estos 5 requisitos:

| ID | Requisito | Peso | ¿Crítico? | Señales de búsqueda |
|---|---|---|---|---|
| `process_areas` | Áreas o zonas de proceso evaluadas | 20 | Sí | áreas, zonas, proceso, ambiente, instalaciones |
| `microbiological_hazards` | Riesgos microbiológicos identificados | 25 | Sí | microbiológico, patógenos, coliformes, listeria, salmonella |
| `sanitation_measures` | Medidas de saneamiento, limpieza y desinfección | 20 | Sí | limpieza, saneamiento, desinfección, sanitización |
| `monitoring_controls` | Controles actuales de monitoreo ambiental | 20 | No | monitoreo, muestreo, verificación, control |
| `area_classification` | Categorización o clasificación de áreas | 15 | No | categorización, clasificación, área crítica |

**Niveles de gate:**

- `OPEN` → score ≥ 75 Y ningún requisito crítico faltante → procede sin interrupción
- `PARTIAL` → score ≥ 40 Y ningún requisito crítico faltante → procede con advertencia
- `BLOCKED` → score < 40 O falta al menos un requisito crítico → detiene ejecución

### 5.2 `analyze_environmental_risks`

Identifica los riesgos microbiológicos ambientales por área de proceso. Usa el contexto del cliente para detectar qué áreas están presentes y genera amenazas con valores de Severidad (1–4) y Ocurrencia (1–3) según la metodología MRO.

**Input:**
```python
context: str              # Contexto completo del cliente
gate_result_json: str     # Output de validate_environmental_context (JSON string)
company_name: str
process_area: str
```

**Output:** `EnvironmentalAnalysisResult` → JSON con amenazas detectadas.

**Áreas analizadas por defecto (6 patrones):**

| Área | Categoría | Riesgo típico |
|---|---|---|
| Recepción y almacenamiento de materias primas | Alta criticidad | Coliformes, E. coli, Salmonella, mohos |
| Área de procesamiento / producción | Alta criticidad | Listeria, Salmonella, Staphylococcus |
| Área de envasado / empaque | Alta criticidad | Mohos, levaduras, Enterobacterias |
| Cámaras de refrigeración / congelación | Media criticidad | Listeria, Pseudomonas, mohos psicrófilos |
| Área de servicios e instalaciones | Media criticidad | Pseudomonas, Coliformes, Legionella |
| Área de personal / vestidores | Baja criticidad | Staphylococcus, Coliformes fecales |

### 5.3 `generate_environmental_monitoring_xlsx`

Genera el archivo XLSX con el formato oficial de Análisis de Riesgo de Monitoreo Ambiental Microbiológico (basado en `ambiental.xlsx`).

**Input:**
```python
threats_json: str     # Output de analyze_environmental_risks (JSON string)
company_name: str
process_area: str
gate_result_json: str # Output de validate_environmental_context
```

**Output:** `EnvironmentalExportResult` → JSON con ruta del archivo generado.

**Estructura del XLSX generado:**

**Hoja 1: "Identificación de servicios"**

Columnas en orden exacto (A–N):
1. Area, Proceso o Servicio
2. CATEGORIZACIÓN DE AREA
3. Riesgos microbiológicos
4. Qué activa el riesgo
5. Habilidades de limpieza/saneamiento
6. Severidad (1–4)
7. Ocurrencia (1–3)
8. Nivel Riesgo (1–12)
9. Medidas especiales de control
10. Frecuencia de verificación
11. Responsables y fechas (en blanco para llenar manualmente)
12. Severidad residual
13. Ocurrencia residual
14. Nivel Riesgo residual esperado

**Hoja 2: "Criterios de evaluación"**

Matriz de riesgo MRO (Severidad × Ocurrencia) con códigos de color:
- High (≥9) → rojo
- Medium (4–8) → amarillo
- Low (1–3) → verde

---

## 6. Flujo de uso obligatorio

```
1. validate_environmental_context(contexto_del_cliente)
   ├── BLOCKED → Mostrar mensaje al usuario. No continuar.
   ├── PARTIAL → Preguntar si desea continuar.
   └── OPEN → Proceder.

2. analyze_environmental_risks(contexto, gate_result, empresa, area)

3. generate_environmental_monitoring_xlsx(threats, empresa, area, gate_result)
```

---

## 7. Matriz de riesgo (MRO)

| | Raro (1) | Posible (2) | Frecuente (3) |
|---|---|---|---|
| **Crítico (4)** | 4 (Medio) | 8 (Medio) | 12 (Alto) |
| **Significativo (3)** | 3 (Bajo) | 6 (Medio) | 9 (Alto) |
| **Menor (2)** | 2 (Bajo) | 4 (Medio) | 6 (Medio) |
| **Insignificante (1)** | 1 (Bajo) | 2 (Bajo) | 3 (Bajo) |

Niveles:
- **High**: ≥ 9 → Rojo
- **Medium**: 4–8 → Amarillo
- **Low**: 1–3 → Verde

---

## 8. Historial de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-05-20 | 1.1.0 | Adición de herramientas de Control de Plagas (MIP) |

### Archivos modificados (v1.1.0):
- `models.py` — Se agregaron 4 modelos: `PestContextValidation`, `PestThreat`, `PestAnalysisResult`, `PestExportResult`
- `server.py` — Se agregaron 3 tools: `validate_pest_context`, `analyze_pest_risks`, `generate_pest_management_xlsx`

### Archivos creados (v1.1.0):
- `services/pest_management_service.py` — Lógica de validación de contexto (candado) y análisis de riesgos con 8 patrones de áreas MIP
- `exporters/pest_management_exporter.py` — Exportación a XLSX con formato profesional idéntico a `MIP.xlsx`

---

# MCP — Control de Plagas (MIP) en Plantas de Alimentos

## Especificación técnica de implementación

---

## 1. Propósito

Servidor MCP que automatiza la evaluación de riesgos del programa de Manejo Integrado de Plagas (MIP) en plantas de alimentos. Dado un contexto de documentos del cliente (áreas operativas, tipos de plagas, causas, controles), el servidor valida que la información mínima esté presente, ejecuta el análisis de riesgos por área y genera el formato oficial en XLSX basado en la plantilla `MIP.xlsx`.

---

## 2. Stack tecnológico

| Componente | Tecnología |
|---|---|
| Framework MCP | `fastmcp` (Python) |
| Transporte | SSE (mismo servidor VIGÍA HACCP) |
| Generación XLSX | `openpyxl` |
| Matriz de riesgo | 5×5 (Severidad 1–5 × Ocurrencia 1–5 = 1–25) |

---

## 3. Estructura de archivos

```
vigia-haccp-mcp/
├── models.py                                                # + Modelos PestManagement
├── services/
│   └── pest_management_service.py           [CREADO v1.1]   # Lógica de validación + análisis
├── exporters/
│   └── pest_management_exporter.py          [CREADO v1.1]   # Generación de XLSX
├── server.py                                                # + 3 nuevas tools MCP
├── MIP.xlsx                                                 # Plantilla de referencia
└── environmental-mcp-spec.md                                # Documentación actualizada
```

---

## 4. Models agregados a `models.py`

### `PestContextValidation`
Valida el resultado del context gate (candado de validación).

| Campo | Tipo | Descripción |
|---|---|---|
| `gate` | `str` | `OPEN`, `PARTIAL` o `BLOCKED` |
| `score` | `int` | Puntaje 0–100 |
| `present` | `list[str]` | IDs de requisitos encontrados |
| `missing` | `list[dict]` | Requisitos faltantes con id, label, why, critical |
| `critical_missing` | `bool` | Si falta algún requisito crítico |
| `user_message` | `Optional[str]` | Mensaje para mostrar al usuario |
| `xlsx_stamp` | `Optional[str]` | Sello que se imprime en el XLSX |
| `can_proceed` | `bool` | Si se puede continuar con el análisis |

### `PestThreat`
Representa una amenaza/riesgo de plaga identificada por área operativa.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `str` | Identificador único (PM001, PM002...) |
| `area` | `str` | Nombre del área operativa |
| `pest_risk` | `str` | Riesgo de presencia de plagas (especies) |
| `potential_causes` | `str` | Causas potenciales |
| `strategic_approach` | `str` | Enfoque estratégico (efecto/daño) |
| `operational_approach` | `str` | Enfoque operativo (condiciones que elevan el riesgo) |
| `severity` | `int` | Severidad (1–5) |
| `occurrence` | `int` | Ocurrencia bioindicadores (1–5) |
| `risk_score` | `int` | Severidad × Ocurrencia (1–25) |
| `risk_level` | `str` | Mínimo / Bajo / Moderado / Alto / Crítico / Extremo |
| `acceptable_threshold` | `str` | Umbral aceptable por plaga en área |
| `plant_actions` | `str` | Acciones recomendadas planta |
| `supplier_actions` | `str` | Acciones recomendadas proveedor |
| `residual_severity` | `int` | Severidad residual esperada |
| `residual_occurrence` | `int` | Ocurrencia residual esperada |
| `residual_risk_score` | `int` | Riesgo residual |
| `residual_risk_level` | `str` | Nivel de riesgo residual |

### `PestAnalysisResult`
Resultado completo del análisis.

| Campo | Tipo | Descripción |
|---|---|---|
| `threats` | `list[PestThreat]` | Lista de amenazas identificadas |
| `total_threats` | `int` | Total de amenazas |
| `high_priority_count` | `int` | Amenazas con riesgo ≥ 12 |
| `analysis_metadata` | `dict` | Metadatos (empresa, área, fecha) |

### `PestExportResult`
Resultado de la exportación a XLSX.

| Campo | Tipo | Descripción |
|---|---|---|
| `file_path` | `str` | Ruta absoluta del archivo |
| `file_name` | `str` | Nombre del archivo |
| `download_url` | `str` | URL de descarga |
| `total_rows` | `int` | Filas totales |
| `high_priority_rows` | `int` | Filas de alta prioridad |

---

## 5. Tools del MCP

### 5.1 `validate_pest_context`

**Context Gate (candado de validación) obligatorio.** Debe llamarse siempre antes de cualquier análisis de control de plagas.

Evalúa si el contexto cubre estos 5 requisitos:

| ID | Requisito | Peso | ¿Crítico? | Señales de búsqueda |
|---|---|---|---|---|
| `operational_areas` | Descripción de áreas operativas de la planta | 20 | Sí | áreas, zonas, instalaciones, planta, operativas |
| `pest_types` | Identificación de tipos de plagas | 25 | Sí | plagas, roedores, insectos, aves, ratas, cucarachas |
| `pest_causes` | Causas potenciales de presencia de plagas | 20 | Sí | causas, diseño sanitario, aberturas, puertas, drenajes |
| `current_controls` | Controles actuales y monitoreo | 20 | No | control, monitoreo, bioindicadores, estaciones, trampas |
| `action_plans` | Acciones correctivas y plan de acción | 15 | No | acciones, correctivas, plan, planta, proveedor |

**Niveles de gate:**
- `OPEN` → score ≥ 75 Y ningún requisito crítico faltante
- `PARTIAL` → score ≥ 40 Y ningún requisito crítico faltante
- `BLOCKED` → score < 40 O falta al menos un requisito crítico

### 5.2 `analyze_pest_risks`

Identifica los riesgos de plagas por área operativa. Usa el contexto del cliente para detectar qué áreas están presentes y genera amenazas con valores de Severidad (1–5) y Ocurrencia (1–5) según la matriz 5×5.

**Input:**
```python
context: str              # Contexto completo del cliente
gate_result_json: str     # Output de validate_pest_context (JSON string)
company_name: str
process_area: str
```

**Output:** `PestAnalysisResult` → JSON con amenazas detectadas.

**Áreas analizadas por defecto (8 patrones):**

| Área | Riesgo típico |
|---|---|
| Almacén de materias primas | Roedores, Tribolium, Gorgojo |
| Área de producción / proceso | Cucarachas, Moscas, Roedores |
| Área de envasado / empaque | Drosophila, Insectos rastreros |
| Cocina / preparación de alimentos | Cucarachas, Moscas, Hormigas |
| Comedor / áreas de consumo | Moscas, Hormigas, Aves |
| Exteriores / perímetros | Aves, Roedores |
| Cuartos de servicio / instalaciones | Roedores, Cucarachas, Alacranes |
| Drenajes y aguas residuales | Rattus norvegicus, Cucarachas, Moscas de drenaje |

### 5.3 `generate_pest_management_xlsx`

Genera el archivo XLSX con el formato oficial de Análisis de Riesgo del programa de Control de Plagas (basado en `MIP.xlsx`).

**Input:**
```python
threats_json: str     # Output de analyze_pest_risks (JSON string)
company_name: str
process_area: str
gate_result_json: str # Output de validate_pest_context
```

**Output:** `PestExportResult` → JSON con ruta del archivo generado.

**Estructura del XLSX generado:**

**Hoja 1: "MIP"**

Columnas (A–O):
1. Descripción de áreas operativas
2. Riesgo de presencia de plagas
3. Causa(s) Potencial(es)
4. Enfoque estratégico
5. Enfoque operativo
6. Severidad (1–5)
7. Ocurrencia Bioindic (1–5)
8. Nivel Riesgo (1–25)
9. Umbral aceptable por plagas en áreas
10. Acciones recomendadas planta
11. Acciones recomendadas proveedor
12. Responsables y fechas (en blanco)
13. Severidad residual
14. Ocurrencia residual
15. Nivel Riesgo residual esperado

**Hoja 2: "Criterios Evaluación"**
- Tabla de severidad (1–5)
- Matriz de riesgo 5×5 con códigos de color
- Tabla de ocurrencia (1–5)

---

## 6. Matriz de riesgo (MIP 5×5)

| Severidad \ Ocurrencia | Baja (1) | Moderada (2) | Alta (3) | Muy Alta (4) | Catastrófica (5) |
|---|---|---|---|---|---|
| **Muy Baja (1)** | 1 (Mínimo) | 2 (Bajo) | 3 (Bajo) | 4 (Moderado) | 5 (Moderado) |
| **Baja (2)** | 2 (Bajo) | 4 (Moderado) | 6 (Alto) | 8 (Alto) | 10 (Alto) |
| **Moderada (3)** | 3 (Bajo) | 6 (Alto) | 9 (Alto) | 12 (Crítico) | 15 (Crítico) |
| **Alta (4)** | 4 (Moderado) | 8 (Alto) | 12 (Crítico) | 16 (Crítico) | 20 (Crítico) |
| **Muy Alta (5)** | 5 (Moderado) | 10 (Alto) | 15 (Crítico) | 20 (Crítico) | 25 (Extremo) |

Niveles:
- **Extremo**: 25 → Negro
- **Crítico**: 12–20 → Rojo
- **Alto**: 6–10 → Naranja
- **Moderado**: 4–5 → Amarillo
- **Bajo**: 2–3 → Verde claro
- **Mínimo**: 1 → Verde oscuro

---

## 7. Historial de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-05-20 | 1.0.0 | Creación de herramientas de Monitoreo Ambiental |
| 2026-05-20 | 1.1.0 | Adición de herramientas de Control de Plagas (MIP) |

### Archivos modificados (v1.1.0):
- `models.py` — Se agregaron 4 modelos: `PestContextValidation`, `PestThreat`, `PestAnalysisResult`, `PestExportResult`
- `server.py` — Se agregaron 3 tools: `validate_pest_context`, `analyze_pest_risks`, `generate_pest_management_xlsx`

### Archivos creados (v1.1.0):
- `services/pest_management_service.py` — Lógica de validación de contexto (candado) y análisis de riesgos con 8 patrones de áreas MIP
- `exporters/pest_management_exporter.py` — Exportación a XLSX con formato profesional idéntico a `MIP.xlsx`

