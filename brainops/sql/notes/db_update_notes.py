"""
sql/db_update_notes.py.
"""

from __future__ import annotations

from typing import Any

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger

# Colonnes autorisées à la mise à jour
_ALLOWED_COLUMNS: set[str] = {
    "parent_id",
    "title",
    "file_path",
    "folder_id",
    "category_id",
    "subcategory_id",
    "status",
    "summary",
    "source",
    "author",
    "project",
    "created_at",
    "modified_at",
    "word_count",
    "content_hash",
    "source_hash",
    "lang",
    "media_id",
}


@with_child_logger
def update_obsidian_note(
    note_id: int,
    updates: dict[str, Any],
    *,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    update_obsidian_note _summary_

    _extended_summary_

    Args:
        note_id (int): _description_
        updates (Dict[str, Any]): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        bool: _description_
    """
    logger = ensure_logger(logger, __name__)
    if not updates:
        logger.debug("[NOTES] Aucun champ à mettre à jour (id=%s)", note_id)
        return False

    # Filtrage strict pour éviter l'injection via les clés
    filtered = {k: v for k, v in updates.items() if k in _ALLOWED_COLUMNS}
    if not filtered:
        logger.warning("[NOTES] Aucun champ autorisé dans updates: %s", list(updates.keys()))
        return False

    set_clause = ", ".join(f"{k} = %s" for k in filtered.keys())
    values = [*list(filtered.values()), note_id]

    conn = get_db_connection(logger=logger)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE obsidian_notes SET {set_clause} WHERE id = %s",
                values,
            )
            conn.commit()
    except Exception as exc:
        raise BrainOpsError("update note DB KO", code=ErrCode.DB, ctx={"note_id": note_id}) from exc
    finally:
        conn.close()
    logger.info("[NOTES] Mise à jour OK (id=%s): %s", note_id, list(filtered.keys()))
    return True


@with_child_logger
def update_obsidian_tags(note_id: int, tags: list[str], logger: LoggerProtocol | None = None) -> None:
    """
    update_obsidian_tags _summary_

    _extended_summary_

    Args:
        note_id (int): _description_
        tags (Dict[str, Any]): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.
    """
    logger = ensure_logger(logger, __name__)
    # Ouvre la connexion à la base de données
    conn = get_db_connection(logger=logger)
    with get_dict_cursor(conn) as cur:
        try:
            # Supprimer les anciens tags associés à cette note
            safe_execute_dict(cur, "DELETE FROM obsidian_tags WHERE note_id = %s", (note_id,))

            # Ajouter les nouveaux tags
            for tag in tags:
                safe_execute_dict(
                    cur,
                    "INSERT INTO obsidian_tags (note_id, tag) VALUES (%s, %s)",
                    (note_id, tag),
                )

            # Commit les changements
            conn.commit()
            logger.info("[TAGS] Tags mis à jour pour la note %d.", note_id)

        except Exception as exc:
            raise BrainOpsError("update tags DB KO", code=ErrCode.DB, ctx={"note_id": note_id}) from exc
        finally:
            # Fermer le curseur et la connexion
            cur.close()
            conn.close()
