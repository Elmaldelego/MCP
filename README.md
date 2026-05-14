# VIGÍA HACCP MCP Server

Servidor MCP que genera análisis HACCP completos, enriquecidos con datos
reales de retiros de mercado de la FDA (openFDA).

**Compatible con:** SurfSense, Claude Desktop, cualquier cliente MCP estándar (SSE).

---

## Estructura del proyecto

```
vigia-haccp-mcp/
├── server.py                  # Punto de entrada — FastMCP + 3 herramientas
├── models.py                  # Modelos Pydantic compartidos
├── services/
│   ├── openfda.py             # Cliente openFDA con manejo de errores
│   └── haccp_generator.py     # Lógica HACCP (PCCs, peligros, límites…)
├── exporters/
│   └── excel_exporter.py      # Exportación Excel con formato profesional
├── requirements.txt
├── .env.example
└── README.md
```

---

## Herramientas MCP expuestas

| Herramienta | Cuándo usarla |
|---|---|
| `get_process_step_schema` | **Primero** — obtén el schema para construir los pasos |
| `search_fda_recalls` | Diagnóstico de peligros reales en FDA |
| `generate_haccp_analysis` | Análisis completo → JSON + Excel |

---

## Instalación local

```bash
# 1. Clonar y entrar al directorio
cd vigia-haccp-mcp

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Editar .env si es necesario

# 5. Iniciar el servidor
python server.py
# → Escuchando en http://0.0.0.0:8000/sse
```

---

## Conectar a SurfSense

1. Inicia el servidor: `python server.py`
2. En SurfSense → **Settings → MCP Servers → Add Server**
3. Configura:
   ```
   Name:      VIGÍA HACCP
   URL:       http://localhost:8000/sse
   Transport: SSE
   ```
4. Guarda y verifica que aparezcan las 3 herramientas en el panel de tools.

### En producción (Railway / VPS)

```
URL: https://tu-dominio.railway.app/sse
```

SurfSense puede conectarse a servidores remotos siempre que el endpoint `/sse`
sea accesible públicamente.

---

## Flujo de uso en SurfSense

```
Usuario: "Genera el análisis HACCP para jamón cocido rebanado"
    ↓
SurfSense LLM consulta la knowledge base del cliente
    ↓
LLM llama: get_process_step_schema()          ← conoce el formato
    ↓
LLM extrae pasos del proceso de la KB
    ↓
LLM llama: generate_haccp_analysis(
    product_name="Jamón cocido rebanado",
    process_steps_json="[...]",
    focus_areas="Listeria, Salmonella",
    fda_product_keyword="cooked ham"
)
    ↓
Servidor consulta openFDA → detecta peligros
    ↓
Genera tabla HACCP + guarda Excel
    ↓
Retorna JSON con análisis completo al usuario
```

---

## Deploy en Railway

```bash
# railway.toml (crear en la raíz)
[build]
  builder = "NIXPACKS"

[deploy]
  startCommand = "python server.py"
  healthcheckPath = "/"
```

Variables de entorno en Railway:
```
PORT        = (Railway lo asigna automáticamente)
HOST        = 0.0.0.0
OUTPUT_DIR  = /tmp/vigia_outputs
LOG_LEVEL   = INFO
```

---

## Notas técnicas

- **Transporte:** SSE (Server-Sent Events) — estándar MCP para servidores remotos.
- **openFDA:** Se consultan los últimos 5 años de retiros alimentarios. No requiere API key.
- **Excel:** Se guarda en `OUTPUT_DIR`. En Railway, es volátil (`/tmp`); considera montar un volumen persistente o subir a S3/R2 si necesitas conservar los archivos.
- **PCCs determinados por:** temperatura de proceso, nombre de etapa, y peligros confirmados en retiros FDA.
- **Normativas de referencia:** NOM-251-SSA1-2009, NOM-213-SSA1-2018, Codex CAC/RCP 1-1969 Rev.4.
