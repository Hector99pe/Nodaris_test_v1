import json
from pathlib import Path

import pytest

from agent import Config, graph

pytestmark = pytest.mark.anyio

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "test_exam_anomalias.json"


def _load_exam_payload() -> dict:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


@pytest.mark.langsmith
@pytest.mark.skipif(not Config.OPENAI_API_KEY, reason="OPENAI_API_KEY no configurada")
async def test_agent_e2e_full_exam_anomaly_dataset() -> None:
    payload = _load_exam_payload()

    inputs = {
        "exam_data": payload,
        "usuario_query": (
            "Audita este examen completo. "
            "Calcula estadísticas, detecta plagio, abandono NR y tiempos sospechosos. "
            "Genera un reporte final verificable."
        ),
    }

    result = await graph.ainvoke(inputs)

    assert result["status"] == "completed"
    assert result.get("hash")
    assert result.get("reporte_final")
    assert result.get("anomalia_detectada") is True

    exam_data = result.get("exam_data") or {}
    students_data = result.get("students_data") or []
    assert exam_data.get("examen", {}).get("id") == payload["examen"]["id"]
    assert len(students_data) == len(payload["resultados"])

    copias = result.get("copias_detectadas") or []
    assert copias
    assert any(
        {caso.get("estudiante1"), caso.get("estudiante2")} == {"70112233", "70223344"}
        for caso in copias
    )

    respuestas_nr = set(result.get("respuestas_nr") or [])
    assert {"70334455", "70778899"}.issubset(respuestas_nr)

    tiempos = set(result.get("tiempos_sospechosos") or [])
    assert {"70334455", "70556677"}.issubset(tiempos)

    reporte = result["reporte_final"]
    assert "REPORTE DE AUDITORÍA ACADÉMICA" in reporte
    assert payload["examen"]["id"] in reporte
