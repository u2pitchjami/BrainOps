"""
sql/db_update_medias.py.
"""

from __future__ import annotations

from typing import Any

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger

# Colonnes autorisées à la mise à jour
_ALLOWED_COLUMNS_MEDIAS: set[str] = {
    "media_type",
    "semantic_type",
    "provider",
    "source_url",
    "storage_path",
}


@with_child_logger
def update_obsidian_medias(
    media_id: int,
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
        logger.debug("[MEDIA] Aucun champ à mettre à jour (id=%s)", media_id)
        return False

    # Filtrage strict pour éviter l'injection via les clés
    filtered = {k: v for k, v in updates.items() if k in _ALLOWED_COLUMNS_MEDIAS}
    if not filtered:
        logger.warning("[MEDIA] Aucun champ autorisé dans updates: %s", list(updates.keys()))
        return False

    set_clause = ", ".join(f"{k} = %s" for k in filtered.keys())
    values = [*list(filtered.values()), media_id]

    conn = get_db_connection(logger=logger)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE medias SET {set_clause} WHERE id = %s",
                values,
            )
            conn.commit()
    except Exception as exc:
        raise BrainOpsError("update MEDIA DB KO", code=ErrCode.DB, ctx={"media_id": media_id}) from exc
    finally:
        conn.close()
    logger.info("[MEDIA] Mise à jour OK (id=%s): %s", media_id, list(filtered.keys()))
    return True
