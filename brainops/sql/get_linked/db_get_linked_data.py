"""
# sql/db_get_linked_data.py
"""

from __future__ import annotations

from typing import Any, Literal

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger

What = Literal["note", "tags", "temp_blocks"]


def get_note_linked_data(
    note_id: int, what: What, *, logger: LoggerProtocol | None = None
) -> dict[str, Any] | list[str]:
    """
    Récupère des informations liées à une note à partir de son id.

    Retour:
      - 'note' / 'category' / 'subcategory' / 'folder' → dict (ou {"error": ...})
      - 'tags' → list[str]
      - 'temp_blocks' → dict (ou {"error": ...})
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)

    try:
        with get_dict_cursor(conn) as cur:
            # Base: la note
            note = safe_execute_dict(
                cur,
                "SELECT * FROM obsidian_notes WHERE id=%s",
                (note_id,),
                logger=logger,
            ).fetchone()
            if not note:
                raise BrainOpsError("Note id KO", code=ErrCode.DB, ctx={"note_id": note_id})

            note_dict = note
            if what == "note":
                return note_dict

            if what == "tags":
                rows_tags = safe_execute_dict(
                    cur,
                    "SELECT tag FROM obsidian_tags WHERE note_id=%s",
                    (note_id,),
                    logger=logger,
                ).fetchall()
                rows_tags_list = [r["tag"] for r in rows_tags]
                return rows_tags_list
            return []

            if what == "temp_blocks":
                row = safe_execute_dict(
                    cur,
                    "SELECT * FROM obsidian_temp_blocks WHERE note_id=%s",
                    (note_id,),
                    logger=logger,
                ).fetchone()
                return row
            return {}

            raise BrainOpsError("what KO", code=ErrCode.DB, ctx={"note_id": note_id})
    except Exception as exc:
        raise BrainOpsError(
            "Récup get link Note KO",
            code=ErrCode.DB,
            ctx={"note_id": note_id},
        ) from exc
    finally:
        conn.close()
