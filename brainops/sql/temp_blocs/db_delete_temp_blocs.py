"""
sql/db_temp_blocs.py.
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger


def delete_blocs_by_path_and_source(
    note_id: int,
    source: str,
    logger: LoggerProtocol | None = None,
) -> None:
    """
    Supprime des blocs dans obsidian_temp_blocks selon la stratégie:

    - source == "all"  -> purge tous les blocs de la note (par note_id)
    - source contient "*" -> supprime par LIKE sur source pour ce file_path
    - sinon -> supprime exactement (file_path, source)
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)

    with get_dict_cursor(conn) as cur:
        try:
            if source == "all":
                safe_execute_dict(
                    cur,
                    "DELETE FROM obsidian_temp_blocks WHERE note_id = %s",
                    (note_id,),
                )
            elif "*" in source:
                like_pattern = source.replace("*", "%")
                safe_execute_dict(
                    cur,
                    """
                    DELETE FROM obsidian_temp_blocks
                    WHERE note_id = %s
                    AND source LIKE %s
                    """,
                    (note_id, like_pattern),
                )
            else:
                safe_execute_dict(
                    cur,
                    """
                    DELETE FROM obsidian_temp_blocks
                    WHERE note_id = %s
                    AND source = %s
                    """,
                    (note_id, source),
                )

            conn.commit()
            logger.info("[DELETE] Blocs supprimés pour %s (source=%s)", note_id, source)
        except Exception as exc:
            conn.rollback()
            raise BrainOpsError("Delete temp_block KO", code=ErrCode.DB, ctx={"note_id": note_id}) from exc
        finally:
            cur.close()
            conn.close()
