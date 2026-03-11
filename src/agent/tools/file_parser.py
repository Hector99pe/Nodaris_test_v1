"""Tools for parsing and normalizing academic data files.

Handles JSON and CSV file ingestion with LLM-assisted
structure interpretation and human-in-the-loop clarification.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Annotated

from langchain_core.tools import tool as langgraph_tool
from langgraph.prebuilt import InjectedState
from langgraph.types import interrupt

from agent.config import Config


@langgraph_tool
def tool_extraer_datos_archivo(
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Extrae datos crudos de un archivo JSON o CSV subido por el usuario.

    Lee el archivo, extrae headers y filas de datos, y retorna una muestra
    para que el agente interprete la estructura.
    Soporta: .json, .csv
    """
    state = state or {}
    file_path = state.get("file_path", "")

    if not file_path:
        return json.dumps({"tipo": "archivo", "error": "No hay archivo para procesar"})

    path = Path(file_path)
    if not path.exists():
        return json.dumps({"tipo": "archivo", "error": f"Archivo no encontrado: {file_path}"})

    ext = path.suffix.lower()

    try:
        if ext == ".json":
            return _parse_json(path)
        elif ext == ".csv":
            return _parse_csv(path)
        else:
            return json.dumps({"tipo": "archivo", "error": f"Formato no soportado: {ext}. Solo se aceptan .json y .csv"})
    except Exception as e:
        return json.dumps({"tipo": "archivo", "error": f"Error al procesar archivo: {str(e)}"})


@langgraph_tool
def tool_normalizar_datos_examen(
    column_mapping: str,
    state: Annotated[dict, InjectedState] = None,  # type: ignore[assignment]
) -> str:
    """Normaliza datos crudos de un archivo al schema estándar de examen.

    Recibe un mapeo de columnas (generado por el agente tras analizar la estructura)
    y transforma los datos al formato interno.

    Args:
        column_mapping: JSON string con el mapeo de columnas. Ejemplo:
            {"dni_column": "Código", "nombre_column": "Nombre",
             "respuestas_columns": ["R1","R2","R3"],
             "nota_column": "Puntaje"}
    """
    state = state or {}
    file_path = state.get("file_path", "")

    if not file_path:
        return json.dumps({"tipo": "normalizacion", "error": "No hay archivo para normalizar"})

    try:
        mapping = json.loads(column_mapping)
    except json.JSONDecodeError:
        return json.dumps({"tipo": "normalizacion", "error": "column_mapping no es JSON válido"})

    path = Path(file_path)
    ext = path.suffix.lower()

    try:
        if ext == ".csv":
            rows, headers = _read_csv_full(path)
        elif ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps({"tipo": "normalizacion", "datos": data, "mensaje": "JSON ya está en formato nativo"})
        else:
            return json.dumps({"tipo": "normalizacion", "error": f"Normalización no soportada para {ext}"})

        # Apply column mapping
        students = _apply_mapping(rows, headers, mapping)

        return json.dumps({
            "tipo": "normalizacion",
            "students_data": students,
            "total_normalizados": len(students),
            "mensaje": f"Normalizados {len(students)} registros de estudiantes"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"tipo": "normalizacion", "error": f"Error al normalizar: {str(e)}"})


@langgraph_tool
def tool_solicitar_clarificacion(
    pregunta: str,
    contexto: str = "",
    opciones: str = "",
) -> str:
    """Solicita aclaración al usuario cuando los datos son ambiguos.

    Pausa la ejecución del agente y espera respuesta del usuario.
    Usar cuando:
    - La estructura del archivo no es clara
    - Hay columnas ambiguas que podrían ser diferentes campos
    - Faltan datos esperados
    - Se necesita confirmar un mapeo de datos

    Args:
        pregunta: Pregunta clara y específica para el usuario
        contexto: Información adicional para que el usuario entienda (muestra de datos, etc.)
        opciones: Lista de opciones separadas por '|' (vacío si es pregunta abierta)
    """
    opciones_list = [o.strip() for o in opciones.split("|") if o.strip()] if opciones else []

    payload = {
        "tipo": "clarificacion",
        "pregunta": pregunta,
        "contexto": contexto,
        "opciones": opciones_list,
    }

    if Config.ALLOW_HUMAN_INTERRUPT:
        respuesta = interrupt(payload)
        return f"El usuario respondió: {respuesta}"

    # Autonomous default: avoid blocking the flow waiting for a user response.
    fallback = opciones_list[0] if opciones_list else "continuar_con_mejor_esfuerzo"
    return json.dumps(
        {
            "tipo": "clarificacion_no_bloqueante",
            "pregunta": pregunta,
            "fallback_aplicado": fallback,
            "mensaje": "Se aplico fallback automatico para mantener autonomia.",
        },
        ensure_ascii=False,
    )


# === Internal parsing functions ===

def _parse_json(path: Path) -> str:
    """Parse a JSON file and return its structure."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Determine structure
    info: Dict[str, Any] = {"tipo": "archivo", "formato": "json"}

    if isinstance(data, dict):
        info["keys"] = list(data.keys())
        # Check if it matches exam schema
        if "examen" in data and "preguntas" in data:
            info["schema_detectado"] = "examen_nodaris"
            info["mensaje"] = "Archivo JSON con schema de examen Nodaris detectado"
            info["datos"] = data
        else:
            info["schema_detectado"] = "desconocido"
            info["muestra"] = {k: _summarize_value(v) for k, v in data.items()}
    elif isinstance(data, list):
        info["total_registros"] = len(data)
        if data:
            info["muestra_primer_registro"] = data[0] if isinstance(data[0], dict) else str(data[0])[:200]

    return json.dumps(info, ensure_ascii=False, default=str)


def _parse_csv(path: Path) -> str:
    """Parse a CSV file and return structure + auto-parsed data if possible."""
    import csv as csv_mod

    info: Dict[str, Any] = {
        "tipo": "archivo",
        "formato": "csv",
    }

    # Try common encodings
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                sniffer = csv_mod.Sniffer()
                sample = f.read(4096)
                try:
                    dialect = sniffer.sniff(sample)
                except csv_mod.Error:
                    dialect = csv_mod.excel  # type: ignore[assignment]
                f.seek(0)
                reader = csv_mod.reader(f, dialect)
                all_rows = list(reader)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return json.dumps({"tipo": "archivo", "error": "No se pudo decodificar el archivo CSV"})

    if not all_rows:
        info["vacio"] = True
        return json.dumps(info, ensure_ascii=False)

    headers = all_rows[0]
    sample_rows = all_rows[1:6]  # up to 5 sample rows

    info["headers"] = headers
    info["muestra_filas"] = sample_rows
    info["total_filas_estimado"] = len(all_rows) - 1

    # Auto-detect data structure
    data_rows = all_rows[1:]
    if data_rows:
        headers_lower = [h.lower().strip() for h in headers]
        try:
            from agent.nodes.validation import _try_build_from_tabular
            parsed = _try_build_from_tabular(headers_lower, data_rows)
            if parsed:
                exam_data, students = parsed
                info["auto_parsed"] = True
                info["datos"] = {"exam_data": exam_data, "students_data": students}
                info["mensaje"] = f"CSV auto-parseado: {len(students)} estudiantes detectados"
        except Exception:
            pass

    return json.dumps(info, ensure_ascii=False, default=str)


def _read_csv_full(path: Path) -> tuple:
    """Read all data from a CSV file. Returns (data_rows, headers)."""
    import csv as csv_mod

    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                sniffer = csv_mod.Sniffer()
                sample = f.read(4096)
                try:
                    dialect = sniffer.sniff(sample)
                except csv_mod.Error:
                    dialect = csv_mod.excel  # type: ignore[assignment]
                f.seek(0)
                reader = csv_mod.reader(f, dialect)
                all_rows = list(reader)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return [], []

    if not all_rows:
        return [], []

    headers = all_rows[0]
    data_rows = all_rows[1:]
    return data_rows, headers


def _apply_mapping(
    rows: List[list],
    headers: List[str],
    mapping: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Apply column mapping to transform raw rows into student records."""
    col_index = {h: i for i, h in enumerate(headers)}

    dni_col = mapping.get("dni_column", "")
    nombre_col = mapping.get("nombre_column", "")
    nota_col = mapping.get("nota_column", "")
    resp_cols = mapping.get("respuestas_columns", [])

    students = []
    for row in rows:
        student: Dict[str, Any] = {}

        if dni_col and dni_col in col_index:
            student["dni"] = str(row[col_index[dni_col]] or "")
        if nombre_col and nombre_col in col_index:
            student["nombre"] = str(row[col_index[nombre_col]] or "")
        if nota_col and nota_col in col_index:
            val = row[col_index[nota_col]]
            student["nota"] = float(val) if val is not None else 0
        if resp_cols:
            respuestas = []
            for rc in resp_cols:
                if rc in col_index:
                    val = row[col_index[rc]]
                    respuestas.append(str(val) if val is not None else "NR")
                else:
                    respuestas.append("NR")
            student["respuestas"] = respuestas

        if student:
            students.append(student)

    return students


def _summarize_value(v: Any) -> str:
    """Summarize a value for preview."""
    if isinstance(v, list):
        return f"list[{len(v)} items]"
    elif isinstance(v, dict):
        return f"dict[keys: {list(v.keys())[:5]}]"
    else:
        s = str(v)
        return s[:100] if len(s) > 100 else s
