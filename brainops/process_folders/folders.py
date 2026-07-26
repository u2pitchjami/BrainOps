"""
# process/folders.py
"""

from __future__ import annotations

from pathlib import Path

from brainops.io.paths import to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.utils.logger import LoggerProtocol, ensure_logger


def ensure_folder_exists(folder_path: str | Path, *, logger: LoggerProtocol | None = None) -> bool:
    """
    Crée le dossier physiquement (mkdir -p) si besoin.
    """
    logger = ensure_logger(logger, __name__)
    folder = Path(to_abs(str(folder_path)))
    if folder.exists():
        logger.debug("[FOLDER] déjà présent : %s", folder)
        return True
    try:
        folder.mkdir(parents=False, exist_ok=True)
        return True
    except Exception as exc:
        raise BrainOpsError("folder_exist KO", code=ErrCode.UNEXPECTED, ctx={"folder_path": folder_path}) from exc
    logger.info("[FOLDER] créé : %s", folder)
