"""Academic data validation node."""

import logging
from typing import Dict, Any
from langsmith import traceable

from agent.config import Config

logger = logging.getLogger("nodaris.validation")


def _try_parse_file(file_path: str):
    """Try to parse a file directly into (exam_data, students_data).

    Handles JSON, Excel (.xlsx/.xls) and CSV files with the standard
    Nodaris exam schema or recognizable academic data structure.
    Returns None for unsupported formats or unrecognized schemas.
    """
    import json as _json
    from pathlib import Path as _Path

    path = _Path(file_path)
    if not path.exists():
        return None

    ext = path.suffix.lower()

    if ext == ".json":
        return _try_parse_json(path)
    elif ext in (".xlsx", ".xls"):
        return _try_parse_excel(path)
    elif ext == ".csv":
        return _try_parse_csv(path)
    else:
        return None  # PDF and others: let agent handle via tools


def _try_parse_json(path):
    """Try to parse a JSON file into (exam_data, students_data)."""
    import json as _json

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except (ValueError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    required_keys = {"examen", "preguntas", "estudiantes", "resultados"}
    if not required_keys.issubset(data.keys()):
        return None

    return _normalize_exam_payload({"exam_data": data})


def _try_parse_excel(path):
    """Try to parse an Excel file into (exam_data, students_data).

    Supports two layouts:
    1. Single sheet with student rows (headers: dni, nombre, R1..Rn, etc.)
    2. Multiple sheets matching Nodaris schema (examen, preguntas, etc.)
    """
    try:
        import openpyxl
    except ImportError:
        return None

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return None

    try:
        return _try_parse_excel_workbook(wb)
    finally:
        wb.close()


def _try_parse_excel_workbook(wb):
    """Internal: parse an open workbook."""
    # Strategy 1: single sheet with student data
    ws = wb.active
    if ws is None:
        return None

    rows = list(ws.iter_rows(values_only=True))
    if not rows or len(rows) < 2:
        return None

    headers = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    return _try_build_from_tabular(headers, rows[1:])


def _try_parse_csv(path):
    """Try to parse a CSV file into (exam_data, students_data)."""
    import csv as _csv

    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, "r", encoding=encoding, newline="") as f:
                sniffer = _csv.Sniffer()
                sample = f.read(4096)
                try:
                    dialect = sniffer.sniff(sample)
                except _csv.Error:
                    dialect = _csv.excel  # type: ignore[assignment]
                f.seek(0)
                reader = _csv.reader(f, dialect)
                all_rows = list(reader)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return None

    if not all_rows or len(all_rows) < 2:
        return None

    headers = [str(c).strip().lower() for c in all_rows[0]]
    return _try_build_from_tabular(headers, all_rows[1:])


# Column name aliases for auto-detection
_DNI_ALIASES = {"dni", "codigo", "código", "id", "documento", "carnet", "matricula", "matrícula"}
_NOMBRE_ALIASES = {"nombre", "nombres", "name", "estudiante", "alumno"}
_APELLIDO_ALIASES = {"apellido", "apellidos", "last_name", "surname"}
_NOTA_ALIASES = {"nota", "puntaje", "score", "calificacion", "calificación", "grade"}
_TIEMPO_ALIASES = {"tiempo", "tiempo_total", "tiempo_seg", "time", "duracion", "duración", "tiempo_total_seg"}


def _try_build_from_tabular(headers, data_rows):
    """Try to build (exam_data, students_data) from tabular data.

    Detects columns by matching header names against known aliases.
    Identifies response columns as those starting with 'r' followed by a digit,
    or 'p' followed by a digit, or 'pregunta'.
    """
    if not headers or not data_rows:
        return None

    col_map = {}
    resp_indices = []
    tiempo_idx = None

    for i, h in enumerate(headers):
        h_clean = h.strip().lower()
        if h_clean in _DNI_ALIASES:
            col_map["dni"] = i
        elif h_clean in _NOMBRE_ALIASES:
            col_map["nombre"] = i
        elif h_clean in _APELLIDO_ALIASES:
            col_map["apellido"] = i
        elif h_clean in _NOTA_ALIASES:
            col_map["nota"] = i
        elif h_clean in _TIEMPO_ALIASES:
            tiempo_idx = i
        else:
            # Check for response columns: r1, r2, p1, p2, pregunta1, resp1, etc.
            import re
            if re.match(r'^(r|p|resp|pregunta|q)\s*\d+$', h_clean):
                resp_indices.append(i)

    # Must have at least DNI or nombre to be useful
    if "dni" not in col_map and "nombre" not in col_map:
        return None

    students = []
    for row in data_rows:
        row_cells = list(row)
        if len(row_cells) < len(headers):
            row_cells.extend([None] * (len(headers) - len(row_cells)))

        student = {}
        if "dni" in col_map:
            val = row_cells[col_map["dni"]]
            student["dni"] = str(val).strip() if val is not None else ""
        if "nombre" in col_map:
            val = row_cells[col_map["nombre"]]
            student["nombre"] = str(val).strip() if val is not None else ""
        if "apellido" in col_map:
            val = row_cells[col_map["apellido"]]
            student["apellido"] = str(val).strip() if val is not None else ""
        if "nota" in col_map:
            val = row_cells[col_map["nota"]]
            try:
                student["nota"] = float(val) if val is not None else 0
            except (ValueError, TypeError):
                student["nota"] = 0

        if resp_indices:
            respuestas = []
            for ri in resp_indices:
                val = row_cells[ri] if ri < len(row_cells) else None
                respuestas.append(str(val).strip().upper() if val is not None else "NR")
            student["respuestas"] = respuestas

        if tiempo_idx is not None:
            val = row_cells[tiempo_idx]
            try:
                student["tiempo_total"] = float(val) if val is not None else 0
            except (ValueError, TypeError):
                student["tiempo_total"] = 0

        # Skip empty rows
        if student.get("dni") or student.get("nombre"):
            students.append(student)

    if not students:
        return None

    # Build minimal exam_data
    exam_data = {
        "examen": {"id": "desde_archivo", "curso": "Importado"},
        "preguntas": [],
    }

    # If we have response columns, build question stubs
    if resp_indices:
        for idx, ri in enumerate(resp_indices, 1):
            exam_data["preguntas"].append({"id": idx, "tema": headers[ri]})

    return exam_data, students


def _normalize_exam_payload(state: Dict[str, Any]) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    """Normalize full exam payload to internal exam_data/students_data format.

    Supports both:
    - Already normalized: state.exam_data + state.students_data
    - Full payload in state.exam_data with keys examen/preguntas/estudiantes/resultados
    """
    exam_data = state.get("exam_data") or {}
    students_data = state.get("students_data") or []

    # Already normalized payload
    if "examen" in exam_data and "preguntas" in exam_data and students_data:
        return exam_data, students_data

    # Full payload mode: exam_data contains raw JSON with all sections
    has_full_payload = (
        isinstance(exam_data, dict)
        and "examen" in exam_data
        and "preguntas" in exam_data
        and "estudiantes" in exam_data
        and "resultados" in exam_data
    )
    if not has_full_payload:
        return exam_data, students_data

    estudiantes = exam_data.get("estudiantes", [])
    resultados = exam_data.get("resultados", [])

    estudiantes_by_id = {
        s.get("id", ""): s for s in estudiantes if isinstance(s, dict)
    }

    merged_students: list[Dict[str, Any]] = []
    for resultado in resultados:
        if not isinstance(resultado, dict):
            continue

        estudiante_id = resultado.get("estudiante_id", "")
        base = estudiantes_by_id.get(estudiante_id, {})

        merged_students.append(
            {
                **base,
                "estudiante_id": estudiante_id,
                "respuestas": resultado.get("respuestas", []),
                "tiempo_total": resultado.get("tiempo_total_seg"),
                "tiempo_respuesta": resultado.get("tiempo_pregunta_seg", []),
                "timestamp_inicio": resultado.get("timestamp_inicio"),
                "timestamp_fin": resultado.get("timestamp_fin"),
            }
        )

    normalized_exam_data = {
        "examen": exam_data.get("examen", {}),
        "preguntas": exam_data.get("preguntas", []),
    }
    return normalized_exam_data, merged_students


@traceable(name="validateAcademicData")
def validate_academic_data(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate academic record inputs.

    Args:
        state: Current workflow state (TypedDict)

    Returns:
        Updated state fields with validation results
    """
    # === Conversational / file mode: skip strict validation ===
    has_exam = bool(state.get("exam_data")) or bool(state.get("students_data"))
    has_individual = bool(state.get("dni"))
    has_file = bool(state.get("file_path"))

    logger.info("Validation: has_exam=%s, has_individual=%s, has_file=%s", has_exam, has_individual, has_file)

    if not has_exam and not has_individual:
        # If there's a file, try to parse it directly into state
        if has_file:
            parsed = _try_parse_file(state.get("file_path", ""))
            if parsed:
                exam_data, students_data = parsed
                examen = exam_data.get("examen", {}) if isinstance(exam_data, dict) else {}
                return {
                    "status": "validated",
                    "mensaje": f"Datos de examen válidos ({len(students_data)} estudiantes)",
                    "exam_data": exam_data,
                    "students_data": students_data,
                    "usuario_query": state.get("usuario_query") or f"Auditar examen {examen.get('id', 'desde archivo')}",
                }
            # File exists but couldn't be auto-parsed — let agent handle via tools
            return {
                "status": "validated",
                "mensaje": "Archivo pendiente de extracción",
            }
        # No file, no data — conversational mode
        return {
            "status": "validated",
            "mensaje": "Modo conversacional",
        }

    exam_data, students_data = _normalize_exam_payload(state)

    # === Full exam mode ===
    if exam_data and (students_data or state.get("students_data")):
        preguntas = exam_data.get("preguntas", []) if isinstance(exam_data, dict) else []
        examen = exam_data.get("examen", {}) if isinstance(exam_data, dict) else {}

        if not isinstance(preguntas, list) or not preguntas:
            return {
                "status": "error",
                "mensaje": "Examen inválido: faltan preguntas",
            }

        if not isinstance(students_data, list) or not students_data:
            return {
                "status": "error",
                "mensaje": "Examen inválido: faltan estudiantes/resultados",
            }

        return {
            "status": "validated",
            "mensaje": f"Datos de examen válidos ({len(students_data)} estudiantes)",
            "exam_data": exam_data,
            "students_data": students_data,
            "usuario_query": state.get("usuario_query") or f"Auditar examen {examen.get('id', 'N/A')}",
        }

    # === Individual mode ===
    dni = state.get("dni", "")
    nota = state.get("nota", 0)

    # Validate DNI presence
    if not dni or not str(dni).strip():
        return {
            "status": "error",
            "mensaje": "DNI es requerido",
        }

    # Validate grade range
    if nota < Config.NOTA_MIN or nota > Config.NOTA_MAX:
        return {
            "status": "error",
            "mensaje": f"Nota inválida. Debe estar entre {Config.NOTA_MIN} y {Config.NOTA_MAX}",
        }

    # Validation passed
    return {
        "status": "validated",
        "mensaje": "Datos válidos",
    }
