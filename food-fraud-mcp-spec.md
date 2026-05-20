# MCP — Food Fraud Vulnerability Analyzer
## Especificación técnica para implementación con Claude Code

---

## 1. Propósito

Servidor MCP (Model Context Protocol) que automatiza la evaluación de vulnerabilidades de fraude alimentario. Dado un contexto de documentos del cliente, el servidor valida que la información mínima esté presente, ejecuta el análisis de amenazas y genera el formato oficial de evaluación de riesgo en XLSX — listo para firmar y archivar.

El servidor es consumido por **SurfSense** como cliente MCP. SurfSense actúa como capa RAG: indexa los documentos del cliente y los inyecta como contexto antes de llamar a las tools del MCP.

---

## 2. Stack tecnológico

| Componente | Tecnología |
|---|---|
| Framework MCP | `fastmcp` (Python) |
| Transporte | Streamable HTTP (`/mcp`) |
| Puerto | `8001` |
| Generación XLSX | `openpyxl` |
| Consulta Paperless-ngx | `httpx` (REST API) |
| Base de datos fraudes | JSON estático local (seed inicial) |
| Entorno | Python 3.11+, Docker-compatible |
| Deploy | VPS DigitalOcean (mismo host que SurfSense) |

### Dependencias (`requirements.txt`)
```
fastmcp>=2.0
openpyxl>=3.1
httpx>=0.27
python-dotenv>=1.0
uvicorn>=0.29
```

### Variables de entorno (`.env`)
```
PAPERLESS_URL=http://localhost:8000
PAPERLESS_TOKEN=<token_api_paperless_ngx>
OUTPUT_DIR=/outputs
FRAUD_DB_PATH=/data/fraud_database.json
MCP_HOST=0.0.0.0
MCP_PORT=8001
```

---

## 3. Estructura del proyecto

```
food-fraud-mcp/
├── server.py                  # Punto de entrada, instancia FastMCP
├── tools/
│   ├── __init__.py
│   ├── validate_context.py    # Tool 1: context gate
│   ├── analyze_threats.py     # Tool 2: análisis de amenazas
│   ├── fraud_reference.py     # Tool 3: consulta historial fraudes
│   └── generate_xlsx.py       # Tool 4: generación del formato
├── data/
│   └── fraud_database.json    # Base de adulteraciones conocidas
├── templates/
│   └── food_fraud_template.xlsx  # Plantilla base del formato
├── outputs/                   # XLSX generados (montado como volumen)
├── .env
├── requirements.txt
└── Dockerfile
```

---

## 4. Tools del MCP

### 4.1 `validate_context`

**Descripción:**
Tool de validación obligatoria (context gate). Debe llamarse siempre antes de cualquier análisis. Evalúa si el contexto disponible cubre los 5 requisitos mínimos y retorna uno de tres niveles: `OPEN`, `PARTIAL` o `BLOCKED`.

**Lógica de scoring:**

Cada requisito tiene un peso que suma 100 puntos en total:

| ID | Requisito | Peso | ¿Crítico? |
|---|---|---|---|
| `process_flow` | Diagrama de flujo o descripción del proceso | 20 | Sí |
| `raw_materials` | Lista de materias primas con origen y proveedor | 30 | Sí |
| `current_controls` | Controles actuales documentados | 20 | No |
| `fraud_history` | Base de adulteraciones conocidas | 15 | No |
| `risk_criteria` | Criterios de severidad y ocurrencia (GFSI/FSMA) | 15 | No |

Un requisito se considera **presente** si el texto del contexto contiene al menos una de sus señales clave (lista de strings por requisito, búsqueda case-insensitive).

**Niveles de gate:**

- `OPEN` → score >= 75 Y ningún requisito crítico faltante → procede sin interrupción
- `PARTIAL` → score >= 40 Y ningún requisito crítico faltante → procede con advertencia, espera confirmación del usuario
- `BLOCKED` → score < 40 O falta al menos un requisito crítico → detiene ejecución

**Input:**
```python
available_context: str   # texto completo del contexto inyectado por SurfSense
```

**Output:**
```python
{
  "gate": "OPEN" | "PARTIAL" | "BLOCKED",
  "score": int,                  # 0–100
  "present": list[str],          # IDs de requisitos encontrados
  "missing": list[dict],         # [{id, label, why, critical}, ...]
  "critical_missing": bool,
  "user_message": str | None,    # mensaje listo para mostrar al usuario
  "xlsx_stamp": str | None,      # sello que se imprime en el XLSX generado
  "can_proceed": bool            # True si gate es OPEN o PARTIAL
}
```

**Comportamiento según nivel:**

- `OPEN`: `user_message = None`, `xlsx_stamp = "✅ Análisis verificado — contexto completo"`
- `PARTIAL`: `user_message` lista los faltantes con su impacto, pregunta si desea continuar. `xlsx_stamp = "⚠️ Análisis preliminar — score {n}/100"`
- `BLOCKED`: `user_message` lista faltantes con ícono 🔴 (crítico) o 🟡 (no crítico). `can_proceed = False`

---

### 4.2 `analyze_fraud_threats`

**Descripción:**
Dado el contexto validado, identifica las amenazas de fraude alimentario, genera las causas potenciales y asigna los valores de Severidad y Ocurrencia usando la matriz del formato. Retorna una lista estructurada de amenazas lista para alimentar el generador de XLSX.

**Input:**
```python
context: str              # contexto completo del cliente
gate_result: dict         # output de validate_context (debe tener can_proceed=True)
company_name: str
process_area: str
```

**Output:**
```python
{
  "threats": [
    {
      "id": str,                    # ej. "T001"
      "threat_description": str,    # qué hace que el riesgo esté presente
      "potential_effect": str,      # impacto en producto, proceso, marca
      "potential_causes": list[str],# lista de causas (puede haber varias)
      "severity": str,              # "I" | "II" | "III" | "IV"
      "severity_label": str,        # "Catastrophic" | "Critical" | "Moderate" | "Negligible"
      "occurrence": str,            # "A" | "B" | "C" | "D" | "E"
      "occurrence_label": str,      # "Frequent" | "Likely" | "Occasional" | "Seldom" | "Unlikely"
      "risk_score": int,            # resultado de la matriz (1–20)
      "risk_level": str,            # "Extremely High" | "High" | "Medium" | "Low"
      "current_controls": str,      # controles que ya existen
      "data_confidence": str,       # "high" | "medium" | "low" (según gate score)
      "uncertain": bool             # True si este campo fue inferido sin dato directo
    }
  ],
  "total_threats": int,
  "high_priority_count": int,       # amenazas con risk_score <= 8
  "analysis_metadata": {
    "gate": str,
    "score": int,
    "generated_at": str             # ISO timestamp
  }
}
```

**Matriz de riesgo (referencia para el LLM):**

La matriz combina Severidad (filas I–IV) × Ocurrencia (columnas A–E) y produce un número del 1 al 20. Los valores exactos son:

```
         A    B    C    D    E
I  →     1    2    6    8   12
II →     3    4    7   11   15
III→     5    9   10   14   16
IV →    13   17   18   19   20
```

Niveles de riesgo:
- Extremely High: scores 1–4
- High: scores 5–8
- Medium: scores 9–14
- Low: scores 15–20

**Nota sobre celdas inciertas:**
Cuando `gate = "PARTIAL"`, los campos derivados de requisitos faltantes deben tener `uncertain = True`. El generador de XLSX los resaltará en fondo ámbar.

---

### 4.3 `get_fraud_reference_data`

**Descripción:**
Consulta la base de datos local de adulteraciones conocidas para un ingrediente específico. Enriquece el análisis con métodos de fraude documentados históricamente, lo que mejora la calidad de `threat_description` y `potential_causes`.

También puede consultar Paperless-ngx para recuperar documentos de referencia internos del cliente (auditorías, análisis de autenticidad previos) usando la API REST de Paperless-ngx.

**Input:**
```python
ingredient: str           # nombre del ingrediente (ej. "miel", "aceite de oliva")
category: str | None      # categoría opcional (ej. "lácteos", "grasas", "especias")
use_paperless: bool       # si True, también consulta Paperless-ngx
paperless_tags: list[str] | None  # tags a buscar en Paperless-ngx
```

**Output:**
```python
{
  "ingredient": str,
  "known_fraud_methods": [
    {
      "method": str,           # ej. "dilución con agua"
      "adulterant": str,       # ej. "agua, glucosa"
      "frequency": str,        # "common" | "occasional" | "rare"
      "detection": str,        # métodos analíticos para detectarlo
      "references": list[str]  # fuentes (RASFF, USP, etc.)
    }
  ],
  "vulnerability_index": str,  # "high" | "medium" | "low"
  "price_volatility": str,     # indicador de presión económica
  "paperless_docs": list[dict] | None  # documentos encontrados en Paperless-ngx
}
```

**Estructura del `fraud_database.json`:**

```json
{
  "ingredients": {
    "miel": {
      "vulnerability_index": "high",
      "price_volatility": "high",
      "known_fraud_methods": [
        {
          "method": "Dilución con jarabes de glucosa o fructosa",
          "adulterant": "jarabe de maíz de alta fructosa, glucosa",
          "frequency": "common",
          "detection": "RMN, análisis isotópico C13/C14, cromatografía de azúcares",
          "references": ["USP Food Fraud Database", "RASFF 2022-0341"]
        },
        {
          "method": "Sustitución de origen geográfico",
          "adulterant": "miel importada declarada como local",
          "frequency": "common",
          "detection": "Análisis isotópico, palinología",
          "references": ["EFSA Journal 2023"]
        }
      ]
    },
    "aceite_de_oliva": { ... },
    "leche_en_polvo": { ... },
    "especias": { ... }
  }
}
```

Incluir en el seed inicial al menos: miel, aceite de oliva, leche/lácteos, especias (azafrán, orégano, pimentón), jugos de fruta, carne/proteínas, y granos (quinoa, amaranto).

---

### 4.4 `generate_food_fraud_xlsx`

**Descripción:**
Genera el archivo XLSX con el formato oficial de análisis de fraude alimentario, llenado con los datos del análisis. Usa `openpyxl` para escribir sobre la plantilla base.

**Input:**
```python
threats: list[dict]        # output de analyze_fraud_threats["threats"]
company_name: str
process_area: str
evaluator_name: str
evaluation_date: str       # formato DD/MM/YYYY
gate_result: dict          # output de validate_context
analysis_metadata: dict    # output de analyze_fraud_threats["analysis_metadata"]
```

**Output:**
```python
{
  "file_path": str,         # ruta absoluta del archivo generado en /outputs/
  "file_name": str,         # ej. "food_fraud_acme_planta1_2025-01-15.xlsx"
  "download_url": str,      # URL relativa para descarga desde SurfSense
  "total_rows": int,
  "high_priority_rows": int,
  "stamp_applied": str      # sello aplicado en el archivo
}
```

**Estructura del XLSX generado:**

El archivo tiene dos hojas:

**Hoja 1: "Análisis de Amenazas"**

Columnas en orden exacto:
1. `#` — número de amenaza
2. `Descripción de la Amenaza`
3. `Efecto Potencial`
4. `Causa(s) Potencial(es)`
5. `Severidad` (I/II/III/IV)
6. `Ocurrencia` (A/B/C/D/E)
7. `Nivel de Riesgo (NR)` — valor numérico
8. `Nivel` — Extremely High / High / Medium / Low
9. `Controles Actuales`
10. `Propuestas de Mitigación` — dejar en blanco (para llenar manualmente)
11. `Decisión` — dejar en blanco (A / AM / R)
12. `Responsable`— dejar en blanco
13. `Fecha Límite` — dejar en blanco
14. `Re-evaluación Sev.` — dejar en blanco
15. `Re-evaluación Ocurr.` — dejar en blanco
16. `NR Esperado` — dejar en blanco

**Hoja 2: "Criterios de Evaluación"**

Reproduce la matriz de riesgo del anejo (Severity I–IV × Probability A–E con los valores 1–20 y los niveles de color).

**Reglas de formato:**

- Encabezado de la empresa (fila 1): `company_name` + `process_area` + `evaluation_date`
- Fila de encabezados de columna: fondo azul oscuro, texto blanco, negrita, altura 30px
- Filas de datos: altura 60px mínimo, wrap text activado
- Columna `Nivel de Riesgo`: color de fondo según nivel
  - Extremely High → rojo (`#FF0000`, texto blanco)
  - High → naranja (`#FF6600`, texto blanco)
  - Medium → amarillo (`#FFCC00`, texto negro)
  - Low → verde (`#00CC00`, texto negro)
- Celdas con `uncertain = True` (gate PARTIAL): fondo ámbar claro (`#FFF3CD`)
- Fila de sello al final del documento: texto del `xlsx_stamp` en cursiva, gris
- Anchos de columna: ajustados al contenido con mínimo razonable por columna

---

## 5. System prompt para el agente en SurfSense

Este prompt se configura en SurfSense al registrar el MCP como conector:

```
Eres un asistente especializado en análisis de fraude alimentario (Food Fraud).

FLUJO OBLIGATORIO — sigue estos pasos en orden estricto:

1. SIEMPRE llama primero a validate_context() con todo el contexto disponible.

2. Según el gate retornado:
   - BLOCKED: muestra el user_message al usuario. No continúes. No inferras
     información faltante. Espera a que el usuario provea los documentos.
   - PARTIAL: muestra el user_message al usuario. Espera confirmación explícita
     ("sí, continúa" o similar) antes de proceder.
   - OPEN: procede directamente al siguiente paso.

3. Llama a get_fraud_reference_data() para cada ingrediente principal
   identificado en el contexto.

4. Llama a analyze_fraud_threats() con el contexto y los datos de referencia.

5. Llama a generate_food_fraud_xlsx() con los resultados del análisis.

6. Entrega al usuario el archivo generado e indica:
   - Cuántas amenazas fueron identificadas
   - Cuántas son de prioridad alta (NR <= 8)
   - El sello de confianza aplicado al documento

RESTRICCIONES:
- Nunca omitas validate_context() aunque el usuario diga tener toda la información.
- Nunca inventes datos de ingredientes, proveedores o controles.
- Si un dato no está en el contexto y no es inferible con certeza, márcalo como incierto.
- El análisis es un apoyo técnico, no reemplaza la validación del consultor.
```

---

## 6. Registro del MCP en SurfSense

```json
{
  "name": "food-fraud-analyzer",
  "url": "http://localhost:8001/mcp",
  "type": "streamable-http",
  "description": "Generador de análisis de vulnerabilidades de fraude alimentario"
}
```

---

## 7. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /outputs /data

EXPOSE 8001
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## 8. Ejemplo de uso completo (flujo feliz)

```
[SurfSense inyecta contexto del cliente con docs indexados]

→ validate_context(available_context="...proceso de envasado de miel,
   proveedor Apiarios del Sur, origen Yucatán, controles: COA por lote,
   certificado SENASICA, criterios GFSI Food Fraud 2023...")

← { gate: "OPEN", score: 85, can_proceed: true, xlsx_stamp: "✅ Análisis verificado" }

→ get_fraud_reference_data(ingredient="miel", use_paperless=True)

← { known_fraud_methods: [...], vulnerability_index: "high" }

→ analyze_fraud_threats(context="...", gate_result={...}, company_name="Apiarios del Sur SA",
   process_area="Envasado de miel")

← { threats: [T001, T002, T003, T004], total_threats: 4, high_priority_count: 2 }

→ generate_food_fraud_xlsx(threats=[...], company_name="Apiarios del Sur SA", ...)

← { file_name: "food_fraud_apiarios_envasado_2025-01-15.xlsx",
    download_url: "/outputs/food_fraud_apiarios_envasado_2025-01-15.xlsx" }
```

---

## 9. Notas de implementación para Claude Code

1. **`server.py`**: instanciar `FastMCP("food-fraud-analyzer")` y registrar los 4 tools desde sus módulos respectivos. Exponer con `uvicorn` en el puerto configurado en `.env`.

2. **`validate_context.py`**: toda la lógica de scoring, señales y mensajes está definida en la sección 4.1. Los `signals` por requisito son listas de strings en español, búsqueda con `in context.lower()`.

3. **`generate_xlsx.py`**: usar la plantilla `/templates/food_fraud_template.xlsx` si existe; si no, crear el libro desde cero con `openpyxl.Workbook()`. Guardar en `OUTPUT_DIR` con nombre `food_fraud_{company_slug}_{area_slug}_{date}.xlsx`.

4. **`fraud_database.json`**: crear el seed con al menos 8 ingredientes de alto riesgo en México: miel, aguacate, aceite de oliva, leche en polvo, chile/pimentón, orégano, jugo de naranja, carne de res. Fuentes de referencia: USP Food Fraud Database, RASFF, EFSA.

5. **Paperless-ngx**: la integración es opcional por evaluación. Si `PAPERLESS_TOKEN` no está en `.env`, el tool `get_fraud_reference_data` omite la consulta sin error.

6. **Manejo de errores**: todos los tools deben retornar errores como dicts con `{"error": str, "code": str}` en lugar de lanzar excepciones no controladas, para que SurfSense pueda mostrar mensajes útiles al usuario.
