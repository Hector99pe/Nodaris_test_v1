from pathlib import Path

from agent.interfaces.queue_consumer import _archive_file


def test_archive_file_moves_to_target(tmp_path: Path) -> None:
    src_dir = tmp_path / "inbox"
    src_dir.mkdir(parents=True, exist_ok=True)
    src = src_dir / "sample.json"
    src.write_text("{}", encoding="utf-8")

    target = tmp_path / "processed"
    _archive_file(str(src), str(target))

    assert not src.exists()
    assert (target / "sample.json").exists()
