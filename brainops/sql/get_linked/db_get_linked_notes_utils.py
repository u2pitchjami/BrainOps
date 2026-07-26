"""
# sql/db_get_linked_notes_utils.py
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.get_linked.db_get_linked_data import get_note_linked_data
from brainops.utils.logger import LoggerProtocol, ensure_logger


def get_note_lang(note_id: int, *, logger: LoggerProtocol | None = None) -> str:
    """
    Retourne la langue (3 lettres) ou 'inconnu'.
    """
    logger = ensure_logger(logger, __name__)
    data = get_note_linked_data(note_id, "note", logger=logger)
    return str(data.get("lang")) if isinstance(data, dict) and data.get("lang") else "inconnu"


def get_data_for_should_trigger(note_id: int, *, logger: LoggerProtocol | None = None) -> tuple[str, int | None, int]:
    """
    Retourne (status, parent_id, word_count) pour décider si un traitement doit être déclenché.
    """
    logger = ensure_logger(logger, __name__)
    note = get_note_linked_data(note_id, "note", logger=logger)
    if not isinstance(note, dict):
        return "", None, 0
    status = str(note.get("status") or "")
    parent_id = int(note["parent_id"]) if note.get("parent_id") is not None else None
    word_count = int(note.get("word_count") or 0)
    return status, parent_id, word_count


def get_parent_id(note_id: int, *, logger: LoggerProtocol | None = None) -> int | None:
    """
    get_parent_id _summary_

    _extended_summary_

    Args:
        note_id (int): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        Optional[int]: _description_
    """
    logger = ensure_logger(logger, __name__)
    note = get_note_linked_data(note_id, "note", logger=logger)
    if not isinstance(note, dict):
        return None
    return int(note["parent_id"]) if note.get("parent_id") is not None else None


def get_file_path(note_id: int, *, logger: LoggerProtocol | None = None) -> str:
    """
    get_file_path _summary_

    _extended_summary_

    Args:
        note_id (int): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        Optional[str]: _description_
    """
    logger = ensure_logger(logger, __name__)
    note = get_note_linked_data(note_id, "note", logger=logger)
    if not isinstance(note, dict):
        raise BrainOpsError("Aucune données récup", code=ErrCode.DB, ctx={"note_id": note_id})
    return str(note["file_path"])


def get_note_status(note_id: int, *, logger: LoggerProtocol | None = None) -> str:
    """
    get_note_status _summary_

    _extended_summary_

    Args:
        note_id (int): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        Optional[str]: _description_
    """
    logger = ensure_logger(logger, __name__)
    note = get_note_linked_data(note_id, "note", logger=logger)
    if not isinstance(note, dict):
        raise BrainOpsError("Aucune données récup", code=ErrCode.DB, ctx={"note_id": note_id})
    return str(note["status"])


def get_note_wc(note_id: int, *, logger: LoggerProtocol | None = None) -> int:
    """
    get_note_wc _summary_

    _extended_summary_

    Args:
        note_id (int): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        Optional[str]: _description_
    """
    logger = ensure_logger(logger, __name__)
    note = get_note_linked_data(note_id, "note", logger=logger)
    if not isinstance(note, dict):
        raise BrainOpsError("Aucune données récup", code=ErrCode.DB, ctx={"note_id": note_id})
    return int(note["word_count"])
