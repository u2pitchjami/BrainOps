"""
# sql/db_notes_utils.py
"""

from __future__ import annotations

from brainops.models.note import Note
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger


def get_note_by_id(
    note_id: int,
    *,
    logger: LoggerProtocol | None = None,
) -> Note | None:
    """
    Récupère une Note complète depuis la base par file_path (ou src_path).
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)
    try:
        with get_dict_cursor(conn) as cur:
            row = safe_execute_dict(
                cur,
                "SELECT * FROM obsidian_notes WHERE id=%s LIMIT 1",
                (note_id,),
                logger=logger,
            ).fetchone()
            if row:
                return Note.from_row(row)
        return None
    finally:
        conn.close()


def get_note_by_path(
    file_path: str,
    src_path: str | None = None,
    *,
    logger: LoggerProtocol | None = None,
) -> Note | None:
    """
    Récupère une Note complète depuis la base par file_path (ou src_path).
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)
    try:
        with get_dict_cursor(conn) as cur:
            for path in [p for p in (src_path, file_path) if p]:
                row = safe_execute_dict(
                    cur,
                    "SELECT * FROM obsidian_notes WHERE file_path=%s LIMIT 1",
                    (path,),
                    logger=logger,
                ).fetchone()
                if row:
                    return Note.from_row(row)
        return None
    finally:
        conn.close()


def file_path_exists_in_db(
    file_path: str,
    src_path: str | None = None,
    *,
    logger: LoggerProtocol | None = None,
) -> int | None:
    """
    Retourne note_id si file_path (ou src_path) existe, sinon None.
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)
    if not conn:
        return None
    try:
        with get_dict_cursor(conn) as cur:
            for path in [p for p in (src_path, file_path) if p]:
                row = safe_execute_dict(
                    cur,
                    "SELECT id FROM obsidian_notes WHERE file_path=%s LIMIT 1",
                    (path,),
                    logger=logger,
                ).fetchone()
                if row:
                    return int(row["id"])
        return None
    finally:
        conn.close()
