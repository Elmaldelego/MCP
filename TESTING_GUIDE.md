# VIGÍA HACCP MCP — Guía de prueba de tools

Servidor MCP con 18 herramientas para análisis de inocuidad alimentaria.

> **Endpoint**: `http://<IP>:8001/sse`

---

## 1. HACCP (Análisis de Peligros)

### `get_process_step_schema`
Obtén el schema JSON para construir los pasos de proceso.
```json
{}
```

### `search_fda_data`
Busca retiros y eventos adversos en openFDA.
```json
{
  "product_name": "cheese",
  "hazard_types": "Listeria, Salmonella",
  "years": 5
}
```

### `generate_haccp_analysis`
Genera análisis HACCP completo + Excel.
```json
{
  "product_name": "Queso Fresco Tipo Panela",
  "process_steps_json": "[{\"step_number\":1,\"step_name\":\"Recepcion de leche cruda\",\"step_type\":\"receiving\",\"time_temperature_profile\":{\"temperature_celsius\":4.0,\"duration_minutes\":null,\"target_unit\":\"leche cruda\"},\"notes\":\"Proveedores locales. Se verifica temperatura, acidez, prueba de alcohol y antibióticos.\"},{\"step_number\":2,\"step_name\":\"Pasteurizacion\",\"step_type\":\"processing\",\"time_temperature_profile\":{\"temperature_celsius\":72.0,\"duration_minutes\":0.25,\"target_unit\":\"temperatura interna del producto\"},\"notes\":\"Pasteurizacion a 72°C por 15 segundos. Intercambiador de placas PHE. PCC-1.\"},{\"step_number\":3,\"step_name\":\"Enfriamiento e inoculacion\",\"step_type\":\"processing\",\"time_temperature_profile\":{\"temperature_celsius\":32.0,\"duration_minutes\":30.0,\"target_unit\":\"temperatura interna\"},\"notes\":\"Enfriamiento a 32°C para inoculacion de cultivo.\"},{\"step_number\":4,\"step_name\":\"Coagulacion\",\"step_type\":\"processing\",\"time_temperature_profile\":{\"temperature_celsius\":32.0,\"duration_minutes\":45.0,\"target_unit\":\"temperatura de cuajado\"},\"notes\":\"Adicion de cuajo. Coagulacion por 45 min.\"},{\"step_number\":5,\"step_name\":\"Corte y desuerado\",\"step_type\":\"processing\",\"time_temperature_profile\":{\"temperature_celsius\":32.0,\"duration_minutes\":20.0,\"target_unit\":\"cuajada\"},\"notes\":\"Corte con liras. Desuerado parcial.\"},{\"step_number\":6,\"step_name\":\"Moldeo y prensado\",\"step_type\":\"processing\",\"time_temperature_profile\":{\"temperature_celsius\":25.0,\"duration_minutes\":120.0,\"target_unit\":\"ambiente\"},\"notes\":\"Moldeo manual en moldes de acero inoxidable. Prensado progresivo 2 horas.\"},{\"step_number\":7,\"step_name\":\"Empacado al vacio\",\"step_type\":\"packaging\",\"time_temperature_profile\":{\"temperature_celsius\":6.0,\"duration_minutes\":null,\"target_unit\":\"ambiente de empaque\"},\"notes\":\"Empacado al vacio en bolsas de barrera. Termosellado.\"},{\"step_number\":8,\"step_name\":\"Almacenamiento en refrigeracion\",\"step_type\":\"storage\",\"time_temperature_profile\":{\"temperature_celsius\":4.0,\"duration_minutes\":null,\"target_unit\":\"camara de refrigeracion\"},\"notes\":\"Almacen a 2-4°C. Producto terminado.\"}]",
  "focus_areas": "Listeria, Salmonella, E. coli",
  "fda_product_keyword": "fresh cheese"
}
```

---

## 2. Food Fraud (Fraude Alimentario)

### `validate_context`
Valida contexto obligatorio (gate).
```json
{
  "available_context": "La empresa procesa miel de abeja en una planta de envasado. Se recibe miel cruda de proveedores nacionales e importados. El area de recepcion verifica documentos y etiquetado. El almacen de materia prima mantiene temperatura controlada. El area de produccion realiza filtrado, pasteurizacion y envasado. Se tienen controles de calidad con pruebas de laboratorio. El equipo de aseguramiento de calidad realiza verificaciones periodicas. Se han identificado riesgos de adulteracion con jarabes de maiz y azucares."
}
```

### `get_fraud_reference_data`
Consulta adulteraciones conocidas para un ingrediente.
```json
{
  "ingredient": "honey"
}
```

### `analyze_fraud_threats`
Identifica amenazas de fraude.
```json
{
  "context": "La empresa procesa miel de abeja en una planta de envasado. Se recibe miel cruda de proveedores nacionales e importados. El area de recepcion verifica documentos y etiquetado. El almacen de materia prima mantiene temperatura controlada. El area de produccion realiza filtrado, pasteurizacion y envasado. Se tienen controles de calidad con pruebas de laboratorio. El equipo de aseguramiento de calidad realiza verificaciones periodicas. Se han identificado riesgos de adulteracion con jarabes de maiz y azucares.",
  "gate_result_json": "{\"gate\": \"OPEN\", \"score\": 85, \"present\": [\"fraud_areas\", \"ingredient_types\", \"risk_description\", \"current_controls\", \"verification_methods\"], \"missing\": [], \"critical_missing\": false, \"can_proceed\": true}",
  "company_name": "Mieles del Sur S.A.",
  "process_area": "Planta de Envasado"
}
```

### `generate_food_fraud_xlsx`
Genera Excel de fraude.
```json
{
  "threats_json": "[{\"id\":\"FF001\",\"threat_description\":\"Adulteracion de miel con jarabe de maiz de alta fructosa\",\"potential_effect\":\"Producto adulterado, perdida de pureza, riesgo de rechazo\",\"potential_causes\":[\"Proveedor deshonesto\",\"Falta de analisis de pureza\"],\"severity\":\"III\",\"severity_label\":\"Moderate\",\"occurrence\":\"C\",\"occurrence_label\":\"Occasional\",\"risk_score\":10,\"risk_level\":\"Medium\",\"current_controls\":\"Pruebas de laboratorio\",\"mitigation_proposals\":\"Implementar analisis C4\",\"data_confidence\":\"Medium\",\"uncertain\":false}]",
  "company_name": "Mieles del Sur S.A.",
  "process_area": "Planta de Envasado",
  "evaluator_name": "Equipo de Calidad",
  "evaluation_date": "20/05/2026",
  "gate_result_json": "{\"gate\": \"OPEN\", \"score\": 85}",
  "analysis_metadata_json": "{\"gate\": \"OPEN\", \"score\": 85, \"generated_at\": \"2026-05-20T12:00:00\"}"
}
```

---

## 3. Food Defense (Defensa Alimentaria)

### `analyze_food_defense`
Analiza vulnerabilidades de sabotaje.
```json
{
  "context": "La planta de produccion Delcen AT opera 24 horas con acceso de personal en tres turnos. El area de recepcion recibe materias primas de diversos proveedores. El almacen de ingredientes y empaques tiene acceso limitado. El area de produccion cuenta con tanques de leche y lineas de proceso continuo. El area de envasado tiene acceso a empaque final y etiquetas. El sistema de agua potable y vapor es centralizado. El laboratorio de calidad maneja reactivos quimicos. El sistema de refrigeracion y camaras de frio son automatizados. Hay camaras de seguridad en accesos principales pero no en todas las areas de proceso.",
  "company_name": "Delcen AT",
  "process_area": "Planta de Produccion"
}
```

### `generate_food_defense_xlsx`
Genera Excel de Food Defense.
```json
{
  "threats_json": "[{\"id\":\"FD001\",\"threat_description\":\"Sabotaje en tanques de leche\",\"potential_effect\":\"Contaminacion de todo el lote\",\"potential_causes\":[\"Acceso no autorizado a tanques\"],\"severity\":4,\"occurrence\":3,\"risk_score\":12,\"risk_level\":\"High\",\"current_controls\":\"Candados en tanques\",\"mitigation_proposals\":\"Implementar doble candado y bitacora\",\"residual_severity\":2,\"residual_occurrence\":1,\"residual_risk_score\":2,\"residual_risk_level\":\"Low\",\"uncertain\":false}]",
  "company_name": "Delcen AT",
  "process_area": "Planta de Produccion"
}
```

---

## 4. Environmental Monitoring (Monitoreo Ambiental)

### `validate_environmental_context`
```json
{
  "available_context": "La planta de citricos Del Valle opera una linea de lavado de naranjas y produccion de jugo. El area de recepcion recibe fruta fresca del campo. El area de lavado y seleccion utiliza agua clorada. La sala de extraccion de jugo tiene equipos centrifugos. El area de pasteurizacion opera intercambiadores de calor. La sala de envasado es clase 100,000 con flujo laminar. Las camaras de refrigeracion mantienen producto terminado a 4°C. El programa de monitoreo ambiental incluye muestreo de superficies y aire."
}
```

### `analyze_environmental_risks`
```json
{
  "context": "La planta de citricos Del Valle opera una linea de lavado de naranjas y produccion de jugo. El area de recepcion recibe fruta fresca del campo. El area de lavado y seleccion utiliza agua clorada. La sala de extraccion de jugo tiene equipos centrifugos. El area de pasteurizacion opera intercambiadores de calor. La sala de envasado es clase 100,000 con flujo laminar. Las camaras de refrigeracion mantienen producto terminado a 4°C. El programa de monitoreo ambiental incluye muestreo de superficies y aire.",
  "gate_result_json": "{\"gate\":\"OPEN\",\"score\":95,\"present\":[\"env_areas\",\"product_types\",\"risk_description\",\"current_controls\",\"verification_methods\"],\"missing\":[],\"critical_missing\":false,\"can_proceed\":true}",
  "company_name": "Citricos del Valle S. de R.L.",
  "process_area": "Linea de Lavado de Naranjas"
}
```

### `generate_environmental_monitoring_xlsx`
```json
{
  "threats_json": "[{\"id\":\"EM001\",\"area\":\"Area de lavado de naranjas\",\"area_category\":\"Zona húmeda\",\"microbiological_risk\":\"Listeria monocytogenes, Salmonella spp.\",\"risk_activators\":\"Agua estancada, salpicaduras, humedad constante\",\"sanitation_abilities\":\"Limpieza manual con sanitizante\",\"severity\":4,\"occurrence\":3,\"risk_score\":12,\"risk_level\":\"Extremely High\",\"special_controls\":\"Reforzar programa de saneamiento\",\"verification_frequency\":\"Semanal\",\"residual_severity\":2,\"residual_occurrence\":1,\"residual_risk_score\":2,\"residual_risk_level\":\"Low\"}]",
  "company_name": "Citricos del Valle S. de R.L.",
  "process_area": "Linea de Lavado de Naranjas",
  "gate_result_json": "{\"gate\":\"OPEN\",\"score\":95}"
}
```

---

## 5. Pest Management / MIP (Control de Plagas)

### `validate_pest_context`
```json
{
  "available_context": "La planta de alimentos procesados Delcen AT tiene un programa de control de plagas. El area de recepcion tiene puertas con sellos y cortinas sanitarias. El almacen de materia prima cuenta con trampas para roedores y estaciones de monitoreo. El area de produccion tiene mallas en ventanas y trampas de luz para insectos. Los drenajes tienen rejillas y trampas. El area de almacen de producto terminado mantiene orden y limpieza. Se tienen registros de monitoreo de plagas. El programa incluye fumigacion programada por empresa externa certificada."
}
```

### `analyze_pest_risks`
```json
{
  "context": "La planta de alimentos procesados Delcen AT tiene un programa de control de plagas. El area de recepcion tiene puertas con sellos y cortinas sanitarias. El almacen de materia prima cuenta con trampas para roedores y estaciones de monitoreo. El area de produccion tiene mallas en ventanas y trampas de luz para insectos. Los drenajes tienen rejillas y trampas. El area de almacen de producto terminado mantiene orden y limpieza. Se tienen registros de monitoreo de plagas. El programa incluye fumigacion programada por empresa externa certificada.",
  "gate_result_json": "{\"gate\":\"OPEN\",\"score\":90,\"present\":[\"pest_areas\",\"pest_types\",\"risk_description\",\"current_controls\",\"verification_methods\"],\"missing\":[],\"critical_missing\":false,\"can_proceed\":true}",
  "company_name": "Alimentos del Valle S.A.",
  "process_area": "Planta de Produccion"
}
```

### `generate_pest_management_xlsx`
```json
{
  "threats_json": "[{\"id\":\"PM001\",\"area\":\"Almacen de materia prima\",\"pest_risk\":\"Roedores (Rattus norvegicus), insectos rastreros\",\"potential_causes\":\"Mercancia entrante contaminada, empaques con huevos o larvas\",\"strategic_approach\":\"Certificacion de proveedores, inspeccion en recepcion\",\"operational_approach\":\"Trampas de feromonas semanales, monitoreo de estaciones\",\"severity\":4,\"occurrence\":2,\"risk_score\":8,\"risk_level\":\"High\",\"acceptable_threshold\":\"Cero roedores, max 2 insectos/trampa/semana\",\"plant_actions\":\"Reforzar programa de limpieza profunda\",\"supplier_actions\":\"Auditar proveedores de materia prima\",\"residual_severity\":2,\"residual_occurrence\":1,\"residual_risk_score\":2,\"residual_risk_level\":\"Low\"}]",
  "company_name": "Alimentos del Valle S.A.",
  "process_area": "Planta de Produccion",
  "gate_result_json": "{\"gate\":\"OPEN\",\"score\":90}"
}
```

---

## 6. Allergen Management (Gestión de Alérgenos)

### `validate_allergen_context`
```json
{
  "available_context": "La planta Delcen AT maneja alergenos en areas de recepcion, almacen de PT, produccion y envasado. Ingresan leche en polvo, harina de trigo y huevo. Hay controles de limpieza CIP, etiquetado con verificacion por codigo de barras, monitoreo de proteinas residuales. El equipo de calidad realiza verificaciones. Se tienen procedimientos para manejo de contacto cruzado y derrames."
}
```

### `analyze_allergen_risks`
```json
{
  "context": "La planta Delcen AT maneja alergenos en areas de recepcion, almacen de PT, produccion y envasado. Ingresan leche en polvo, harina de trigo y huevo. Hay controles de limpieza CIP, etiquetado con verificacion por codigo de barras, monitoreo de proteinas residuales. El equipo de calidad realiza verificaciones. Se tienen procedimientos para manejo de contacto cruzado y derrames.",
  "gate_result_json": "{\"gate\":\"OPEN\",\"score\":100,\"present\":[\"allergen_areas\",\"allergen_types\",\"risk_description\",\"current_controls\",\"verification_methods\"],\"missing\":[],\"critical_missing\":false,\"can_proceed\":true}",
  "company_name": "Delcen AT",
  "process_area": "Planta de Produccion"
}
```

### `generate_allergen_management_xlsx`
```json
{
  "threats_json": "[{\"id\":\"AL001\",\"area\":\"Almacen de producto terminado\",\"allergens_involved\":\"Lactosa, Soya, Almendra, Colorante Amarillo 5, Gluten\",\"risk_description\":\"Derrames de leche por mal manejo de operadores que contaminan otros productos almacenados. Mal etiquetado.\",\"current_controls\":\"Plan de manejo de alergenos, procedimientos de limpieza por derrames, KIT para limpieza\",\"severity\":\"II\",\"severity_label\":\"Critical\",\"occurrence\":\"B\",\"occurrence_label\":\"Likely\",\"risk_score\":4,\"risk_level\":\"Extremely High\",\"special_controls\":\"NO. Los controles actuales demuestran consistencia.\",\"verification_frequency\":\"Verificacion durante la operacion. Registros. Auto inspecciones rutinarias.\",\"residual_severity\":\"II\",\"residual_occurrence\":\"B\",\"residual_risk_score\":4,\"residual_risk_level\":\"Extremely High\"}]",
  "company_name": "Delcen AT",
  "process_area": "Planta de Produccion",
  "evaluator_name": "Equipo de Calidad Delcen",
  "evaluation_date": "20/05/2026",
  "materials_involved": "Leche, Trigo, Huevo, Soya, Almendra, Lactosa",
  "gate_result_json": "{\"gate\":\"OPEN\",\"score\":100}"
}
```

---

## Flujo de prueba completo (ejemplo integrado)

```
1. validate_allergen_context  → verifica contexto
2. analyze_allergen_risks     → identifica amenazas
3. generate_allergen_management_xlsx → exporta Excel
```

Todos los análisis siguen el mismo patrón:
1. **Validar** contexto (gate)
2. **Analizar** riesgos
3. **Exportar** a Excel
