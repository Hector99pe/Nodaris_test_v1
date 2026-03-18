"""Academic data validation node."""

import json as _json_mod
import logging
import re as _re
from typing import Any, Dict, List

from langsmith import traceable

from agent.config import Config

logger = logging.getLogger("nodaris.validation")

# Semantic roles the LLM (or fallback) can assign to columns
_VALID_ROLES = {
    "dni", "nombre", "apellido", "nota", "tiempo",
    "estado", "respuestas_concat", "respuesta_individual", "ignorar",
}


def _try_parse_file(file_path: str):
    """Try to parse a file directly into (exam_data, students_data).

    Handles JSON and CSV files with the standard Nodaris exam schema
    or recognizable academic data structure.
    Returns None for unsupported formats or unrecognized schemas.
    """
    from pathlib import Path as _Path

    path = _Path(file_path)
    if not path.exists():
        return None

    ext = path.suffix.lower()

    if ext == ".json":
        return _try_parse_json(path)
    elif ext == ".csv":
        return _try_parse_csv(path)
    else:
        return None  # Unsupported format


def _try_parse_json(path):
    """Try to parse a JSON file into (exam_data, students_data)."""
    import json as _json

    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
    except (ValueError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    required_keys = {"examen", "preguntas", "estudiantes", "resultados"}
    if not required_keys.issubset(data.keys()):
        return None

    return _normalize_exam_payload({"exam_data": data})


def _try_parse_csv(path):
    """Try to parse a CSV file into (exam_data, students_data)."""
    import csv as _csv

    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=encoding, newline="") as f:
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


# ── Column mapping: LLM-first, regex fallback ──────────────────────

def _llm_map_columns(headers: List[str], sample_row: list) -> Dict[int, str] | None:
    """Ask the LLM to semantically map each column header to a data role.

    Returns a dict  {column_index: role}  or None when the LLM is unavailable.
    """
    if not Config.OPENAI_API_KEY:
        return None

    try:
        from langchain_openai import ChatOpenAI
        from pydantic import SecretStr

        from agent.resilience import call_with_llm_circuit_breaker

        llm = ChatOpenAI(
            api_key=SecretStr(Config.OPENAI_API_KEY),
            model=Config.OPENAI_MODEL,
            temperature=0.0,
        )

        sample_values = [
            str(v).strip() if v is not None else "" for v in sample_row[: len(headers)]
        ]

        prompt = (
            "Eres un clasificador de columnas para datos académicos de exámenes.\n"
            "Dadas las cabeceras de un archivo tabular y una fila de ejemplo, "
            "asigna a CADA columna exactamente UNO de estos roles:\n\n"
            '  "dni"                  → identificador del estudiante (DNI, código, matrícula, carnet, documento, id)\n'
            '  "nombre"              → nombre o nombre completo del estudiante\n'
            '  "apellido"            → apellido(s) del estudiante\n'
            '  "nota"                → calificación, puntaje, score\n'
            '  "tiempo"              → tiempo empleado (segundos, minutos, duración)\n'
            '  "estado"              → asistencia o estado (asistió, faltó, presente, ausente, retirado, etc.)\n'
            '  "respuestas_concat"   → columna ÚNICA que contiene TODAS las respuestas concatenadas '
            '(ej: "ABCD-EBC", "AABCCDE")\n'
            '  "respuesta_individual"→ columna con la respuesta a UNA sola pregunta (R1, P2, Pregunta3, etc.)\n'
            '  "ignorar"             → columna irrelevante para la auditoría\n\n'
            "Cabeceras: " + _json_mod.dumps(headers, ensure_ascii=False) + "\n"
            "Ejemplo:    " + _json_mod.dumps(sample_values, ensure_ascii=False) + "\n\n"
            "Responde SOLO con un JSON  {índice_columna: rol}  — sin explicaciones.\n"
            'Ejemplo de respuesta: {"0": "dni", "1": "nombre", "2": "nota"}'
        )

        response = call_with_llm_circuit_breaker(lambda: llm.invoke(prompt))
        raw = (response.content or "").strip()

        # Extract JSON from potential markdown fences
        json_match = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if not json_match:
            logger.warning("LLM column mapper: no JSON found in response")
            return None

        parsed = _json_mod.loads(json_match.group())
        mapping: Dict[int, str] = {}
        for k, v in parsed.items():
            idx = int(k)
            role = str(v).strip().lower()
            if role in _VALID_ROLES and 0 <= idx < len(headers):
                mapping[idx] = role

        if mapping:
            logger.info("LLM column mapping: %s", mapping)
        return mapping or None

    except Exception as e:
        logger.warning("LLM column mapping failed, using fallback: %s", e)
        return None


def _fallback_map_columns(headers: List[str]) -> Dict[int, str]:
    """Minimal regex-based column mapping used when the LLM is unavailable."""
    mapping: Dict[int, str] = {}
    for i, h in enumerate(headers):
        h_clean = h.strip().lower()
        if _re.match(r"^(dni|codigo|código|id|documento|carnet|matr[ií]cula)$", h_clean):
            mapping[i] = "dni"
        elif _re.match(r"^(nombre|nombres|estudiante|alumno|name)$", h_clean):
            mapping[i] = "nombre"
        elif _re.match(r"^(apellido|apellidos|last_name|surname)$", h_clean):
            mapping[i] = "apellido"
        elif _re.match(r"^(nota|puntaje|score|calificaci[oó]n|grade)$", h_clean):
            mapping[i] = "nota"
        elif _re.match(r"^(tiempo|tiempo_total|tiempo_seg|time|duraci[oó]n|tiempo_total_seg)$", h_clean):
            mapping[i] = "tiempo"
        elif _re.match(r"^(estado|status|asistencia)$", h_clean):
            mapping[i] = "estado"
        elif _re.match(r"^(respuestas?|responses?|answers?)$", h_clean):
            mapping[i] = "respuestas_concat"
        elif _re.match(r"^(r|p|resp|pregunta|q)\s*\d+$", h_clean):
            mapping[i] = "respuesta_individual"
    return mapping


def _try_build_from_tabular(headers, data_rows):
    """Build (exam_data, students_data) from tabular data.

    Uses the LLM to semantically interpret column names.
    Falls back to regex matching when the LLM is unavailable.
    """
    if not headers or not data_rows:
        return None

    # Ask the LLM first; fall back to regex
    mapping = _llm_map_columns(headers, data_rows[0])
    if mapping is None:
        mapping = _fallback_map_columns(headers)

    # Must have at least a dni or nombre column to proceed
    roles_found = set(mapping.values())
    if "dni" not in roles_found and "nombre" not in roles_found:
        return None

    # Collect indices by role
    dni_idx = next((i for i, r in mapping.items() if r == "dni"), None)
    nombre_idx = next((i for i, r in mapping.items() if r == "nombre"), None)
    apellido_idx = next((i for i, r in mapping.items() if r == "apellido"), None)
    nota_idx = next((i for i, r in mapping.items() if r == "nota"), None)
    tiempo_idx = next((i for i, r in mapping.items() if r == "tiempo"), None)
    estado_idx = next((i for i, r in mapping.items() if r == "estado"), None)
    respuestas_concat_idx = next((i for i, r in mapping.items() if r == "respuestas_concat"), None)
    resp_individual_indices = sorted(i for i, r in mapping.items() if r == "respuesta_individual")

    students: List[Dict[str, Any]] = []
    for row in data_rows:
        row_cells = list(row)
        if len(row_cells) < len(headers):
            row_cells.extend([None] * (len(headers) - len(row_cells)))

        student: Dict[str, Any] = {}

        if dni_idx is not None:
            val = row_cells[dni_idx]
            student["dni"] = str(val).strip() if val is not None else ""
        if nombre_idx is not None:
            val = row_cells[nombre_idx]
            student["nombre"] = str(val).strip() if val is not None else ""
        if apellido_idx is not None:
            val = row_cells[apellido_idx]
            student["apellido"] = str(val).strip() if val is not None else ""
        if nota_idx is not None:
            val = row_cells[nota_idx]
            try:
                student["nota"] = float(val) if val is not None else 0
            except (ValueError, TypeError):
                student["nota"] = 0

        if resp_individual_indices:
            respuestas = []
            for ri in resp_individual_indices:
                val = row_cells[ri] if ri < len(row_cells) else None
                respuestas.append(str(val).strip().upper() if val is not None else "NR")
            student["respuestas"] = respuestas
        elif respuestas_concat_idx is not None:
            val = row_cells[respuestas_concat_idx] if respuestas_concat_idx < len(row_cells) else None
            raw = str(val).strip().upper() if val is not None else ""
            if raw:
                student["respuestas"] = [
                    "NR" if c in ("-", "_", "*", " ") else c
                    for c in raw
                ]

        if estado_idx is not None:
            val = row_cells[estado_idx]
            student["estado"] = str(val).strip() if val is not None else ""

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
    exam_data: Dict[str, Any] = {
        "examen": {"id": "desde_archivo", "curso": "Importado"},
        "preguntas": [],
    }

    if resp_individual_indices:
        for idx, ri in enumerate(resp_individual_indices, 1):
            exam_data["preguntas"].append({"id": idx, "tema": headers[ri]})
    elif respuestas_concat_idx is not None and students:
        first_resp = students[0].get("respuestas", [])
        for idx in range(1, len(first_resp) + 1):
            exam_data["preguntas"].append({"id": idx, "tema": f"P{idx}"})

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
