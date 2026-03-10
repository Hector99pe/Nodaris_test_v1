"""Tool for copying and managing exam data.

Handles duplication and backup of academic records.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime


def copiar_examen(
    origen: str,
    destino: Optional[str] = None
) -> Dict[str, str]:
    """Copy exam data from origin to destination.

    Args:
        origen: Path to source exam file
        destino: Path to destination (optional, auto-generated if None)

    Returns:
        Dictionary with copy operation status
    """
    origen_path = Path(origen)

    if not origen_path.exists():
        return {
            "status": "error",
            "mensaje": f"Archivo origen no encontrado: {origen}"
        }

    # Auto-generate destination if not provided
    if destino is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = f"{origen_path.stem}_copia_{timestamp}{origen_path.suffix}"

    destino_path = Path(destino)

    try:
        shutil.copy2(origen_path, destino_path)
        return {
            "status": "ok",
            "mensaje": f"Examen copiado exitosamente a {destino}",
            "ruta_destino": str(destino_path)
        }
    except Exception as e:
        return {
            "status": "error",
            "mensaje": f"Error al copiar examen: {str(e)}"
        }


def respaldar_datos(datos: Dict, nombre_backup: str) -> Dict[str, str]:
    """Create a backup of exam data.

    Args:
        datos: Exam data to backup
        nombre_backup: Name for the backup file

    Returns:
        Dictionary with backup operation status
    """
    backup_dir = Path("data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{nombre_backup}_{timestamp}.json"

    try:
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)

        return {
            "status": "ok",
            "mensaje": f"Respaldo creado en {backup_path}",
            "ruta_backup": str(backup_path)
        }
    except Exception as e:
        return {
            "status": "error",
            "mensaje": f"Error al crear respaldo: {str(e)}"
        }
