# Datos de Entrada

Guia de formatos de entrada soportados por Nodaris.

## 1. Formato completo de examen (JSON Nodaris)

Estructura recomendada para auditoria completa:

```json
{
  "examen": {
    "id": "EX-001",
    "curso": "Programacion I",
    "duracion_min": 60
  },
  "preguntas": [{ "id": 1, "tema": "fundamentos", "correcta": "B" }],
  "estudiantes": [{ "id": "E01", "dni": "70112233", "nombre": "Ana" }],
  "resultados": [
    {
      "estudiante_id": "E01",
      "respuestas": ["B", "A", "NR"],
      "tiempo_total_seg": 2200,
      "tiempo_pregunta_seg": [20, 30, 0]
    }
  ]
}
```

Notas:

- `validation.py` normaliza este payload a `exam_data` y `students_data`.
- Si faltan campos secundarios, el flujo puede continuar si hay datos minimos auditables.

## 2. Modo individual

Entrada minima:

```json
{
  "dni": "12345678",
  "nota": 15
}
```

Validaciones base:

- `dni`: 8 digitos.
- `nota`: rango configurado en `Config.NOTA_MIN` y `Config.NOTA_MAX`.

## 3. Modo archivo

Entrada de estado:

```json
{
  "file_path": "data/inbox/examen.csv",
  "file_type": "csv"
}
```

Formatos soportados por parser:

- `.json`
- `.csv`

El parser intenta mapear columnas usando LLM y fallback por regex.

## 4. Campos derivados en estado

Durante la ejecucion, Nodaris puede completar:

- `exam_data`
- `students_data`
- `copias_detectadas`
- `respuestas_nr`
- `tiempos_sospechosos`
- `promedio`
- `distribucion_notas`
- `preguntas_dificiles`
- `hash`
- `reporte_final`

## 5. Recomendaciones de calidad de datos

- Mantener identificadores consistentes entre `estudiantes.id` y `resultados.estudiante_id`.
- Usar `NR` para no respondidas.
- Incluir tiempos si se desea analisis de conducta.
- Evitar columnas ambiguas en CSV; usar encabezados explicitos (`dni`, `nota`, `tiempo_total`).
