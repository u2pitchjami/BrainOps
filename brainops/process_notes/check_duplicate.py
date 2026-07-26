"""
# check_duplicate.py
"""

from __future__ import annotations

from pathlib import Path

from brainops.models.note_context import NoteContext
from brainops.process_import.utils.paths import path_is_inside
from brainops.process_notes.new_note_utils import (
    _handle_duplicate_note,
)
from brainops.sql.notes.db_check_duplicate_note import check_duplicate
from brainops.utils.config import IMPORTS_PATH
from brainops.utils.logger import LoggerProtocol, ensure_logger


def hub_check_duplicate(ctx: NoteContext, *, logger: LoggerProtocol | None = None) -> bool:
    """
    Check if note is a duplicate of another note.

    Args:
        file_path: path to the note to check
        context: note context
        logger: logger
    """
    logger = ensure_logger(logger, __name__)
    # ---- détection doublons pour les imports ------------------------------
    fp = ctx.file_path
    fp_base = ctx.base_fp
    if path_is_inside(IMPORTS_PATH, str(fp_base)):
        is_dup, dup_info = check_duplicate(ctx, logger=logger)
        logger.debug("[DUP] is_dup=%s dup_info=%s", is_dup, dup_info)
        if is_dup:
            new_path = _handle_duplicate_note(Path(fp), dup_info, logger=logger)
            updates = {"file_path": new_path.as_posix(), "status": "duplicate"}
            logger.debug("[NOTES] Mise à jour DB (duplicate): %s", updates)
            return True
        logger.info("[DUP] 👌 Pas de doublon")
        return False
    logger.info("[DUP] Non concernée pour la recherche de doublon")
    return False
