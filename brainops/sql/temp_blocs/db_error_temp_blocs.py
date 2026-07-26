"""
sql/db_temp_blocs.py.
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger


def mark_bloc_as_error(
    *,
    block_id: int,
    logger: LoggerProtocol | None = None,
) -> None:
    """
    Marque un bloc comme étant en erreur à partir de son identifiant SQL.
    """
    current_logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=current_logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                """
                UPDATE obsidian_temp_blocks
                SET status = 'error'
                WHERE id = %s
                  AND status <> 'processed'
                """,
                (block_id,),
            )
            conn.commit()

    except Exception as exc:
        conn.rollback()
        current_logger.exception(
            "Erreur lors du passage du bloc en erreur : block_id=%d",
            block_id,
        )
        raise BrainOpsError(
            "Impossible de marquer le bloc comme étant en erreur",
            code=ErrCode.DB,
            ctx={"block_id": block_id},
        ) from exc

    finally:
        conn.close()
