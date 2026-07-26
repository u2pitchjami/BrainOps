"""
sql/db_temp_blocs.py.
"""

from __future__ import annotations

import json

from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger


def get_blocks_and_embeddings_by_note(
    note_id: int, logger: LoggerProtocol | None = None
) -> tuple[list[str], list[list[float]]]:
    """
    Charge les blocs (content) et leurs embeddings (JSON dans `response`) pour une note donnée.

    Ne retourne jamais None: ([], []) en cas d'erreur.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] get_blocks_and_embeddings_by_note(%s)", note_id)
    conn = get_db_connection(logger=logger)
    if not conn:
        logger.error("[DB] Connexion à la base échouée")
        return [], []

    with get_dict_cursor(conn) as cur:
        try:
            safe_execute_dict(
                cur,
                """
                SELECT block_index, content, response
                FROM obsidian_temp_blocks
                WHERE note_id = %s
                AND source = 'embeddings'
                AND status = 'processed'
                ORDER BY block_index
                """,
                (note_id,),
            )
            rows = cur.fetchall()
        except Exception as e:
            logger.error("[DB] Erreur requête temp_blocks: %s", e)
            return [], []
        finally:
            cur.close()
            conn.close()

    blocks: list[str] = []
    embeddings: list[list[float]] = []

    for row in rows:
        try:
            raw = row["response"]

            # 1er passage: si str, tenter un json.loads
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                parsed = raw

            # Si c’est encore une str qui ressemble à un JSON array → 2e loads
            if isinstance(parsed, str):
                s = parsed.strip()
                if s.startswith("[") and s.endswith("]"):
                    try:
                        parsed = json.loads(s)
                    except Exception:
                        parsed = None

            if isinstance(parsed, list) and parsed:
                vec = [float(x) for x in parsed]
                blocks.append(str(row["content"]))
                embeddings.append(vec)
            else:
                logger.warning("[DB LOAD] Embedding illisible au bloc %s", row["block_index"])

        except Exception as e:
            logger.error(
                "[DB LOAD] Erreur parsing embedding bloc %s : %s",
                row.get("block_index"),
                e,
            )

    return blocks, embeddings
