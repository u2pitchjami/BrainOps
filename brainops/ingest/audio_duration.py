import json
from pathlib import Path
import subprocess

from brainops.utils.logger import LoggerProtocol, ensure_logger


def extract_audio_duration_seconds(
    audio_path: Path,
    *,
    logger: LoggerProtocol | None = None,
) -> int | None:
    """
    Retourne la durée en secondes d'un fichier audio via ffprobe.

    Retourne None si erreur.
    """

    logger = ensure_logger(logger, __name__)

    if not audio_path.exists():
        logger.warning("Fichier audio introuvable: %s", audio_path)
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)
        duration_str = data.get("format", {}).get("duration")

        if duration_str is None:
            logger.warning("Durée introuvable via ffprobe pour %s", audio_path)
            return None

        duration_float = float(duration_str)
        return int(duration_float)

    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Erreur extraction durée audio: %s", exc)
        return None
