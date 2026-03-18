from pathlib import Path

from agent.interfaces.queue_consumer import _archive_file
from agent.interfaces.queue_consumer import _build_completed_summary


def test_archive_file_moves_to_target(tmp_path: Path) -> None:
    src_dir = tmp_path / "inbox"
    src_dir.mkdir(parents=True, exist_ok=True)
    src = src_dir / "sample.json"
    src.write_text("{}", encoding="utf-8")

    target = tmp_path / "processed"
    _archive_file(str(src), str(target))

    assert not src.exists()
    assert (target / "sample.json").exists()


def test_completed_summary_does_not_include_quality_line() -> None:
    result = {
        "confidence_score": 0.91,
        "anomalia_detectada": True,
        "copias_detectadas": [{"nivel_sospecha": "ALTO"}],
        "tiempos_sospechosos": ["x"],
        "respuestas_nr": ["y"],
        "hash": "8873a808abcd",
        "quality_evaluation": "Calidad: ALTA. Coherente con hallazgos.",
    }
    msg = _build_completed_summary(3, "test_examen_01.json", result)
    assert "Evaluación de calidad" not in msg
    assert "Calidad:" not in msg


def test_completed_summary_keeps_core_fields() -> None:
    result = {
        "confidence_score": 0.98,
        "anomalia_detectada": False,
        "hash": "b066f44fabcd",
        "reporte_final": "...\n📊 Calidad del análisis: EXCELENTE\n...",
    }
    msg = _build_completed_summary(4, "test_examen_02.json", result)
    assert "Auditoría completada" in msg
    assert "Confianza" in msg
    assert "Hash" in msg
