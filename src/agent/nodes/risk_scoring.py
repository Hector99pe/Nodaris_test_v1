"""Risk scoring helpers for autonomous job prioritization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _filename_risk(name: str) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if any(k in name for k in ("anomalia", "anomaly", "sospecha", "fraude", "plagio", "risk", "critico")):
        score += 0.5
        reasons.append("keyword_riesgo_en_nombre")
    return score, reasons


def _json_rows(path: Path) -> list[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    rows = data.get("resultados", [])
    return rows if isinstance(rows, list) else []


def _json_behavior_risk(rows: list[Dict[str, Any]]) -> tuple[float, list[str]]:
    if not rows:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    total = len(rows)

    if total >= 30:
        score += 0.2
        reasons.append("volumen_alto")

    nr_count, fast_count = _row_flags(rows)

    if (nr_count / total) >= 0.2:
        score += 0.2
        reasons.append("alto_abandono_detectado")
    if (fast_count / total) >= 0.15:
        score += 0.15
        reasons.append("tiempos_muy_rapidos")

    return score, reasons


def _row_flags(rows: list[Dict[str, Any]]) -> tuple[int, int]:
    nr_count = 0
    fast_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        nr_count += 1 if _is_nr_heavy(row.get("respuestas", [])) else 0
        tiempo = row.get("tiempo_total_seg")
        if isinstance(tiempo, (int, float)) and 0 < tiempo < 1200:
            fast_count += 1
    return nr_count, fast_count


def _is_nr_heavy(respuestas: Any) -> bool:
    if not isinstance(respuestas, list) or not respuestas:
        return False
    empty = sum(1 for r in respuestas if str(r).upper() in ("NR", "", "NONE"))
    return empty >= max(1, len(respuestas) // 2)


def _label_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def score_file_risk(file_path: str) -> Dict[str, Any]:
    """Return a risk profile for a candidate audit file."""
    path = Path(file_path)
    name = path.name.lower()

    score = 0.2
    reasons: list[str] = []

    fname_score, fname_reasons = _filename_risk(name)
    score += fname_score
    reasons.extend(fname_reasons)

    if path.suffix.lower() == ".json":
        jscore, jreasons = _json_behavior_risk(_json_rows(path))
        score += jscore
        reasons.extend(jreasons)

    score = max(0.0, min(1.0, score))
    label = _label_from_score(score)

    return {
        "priority_score": round(score, 3),
        "risk_label": label,
        "reasons": reasons,
    }
