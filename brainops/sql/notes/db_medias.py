"""
# sql/db_medias.py
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.media import Media
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def upsert_media_from_model(
    media: Media,
    *,
    logger: LoggerProtocol | None = None,
) -> int:
    """
    Upsert idempotent par (note_id, storage_path).

    Retourne l'id du media via LAST_INSERT_ID(id).
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                """
                INSERT INTO medias
                  (note_id, media_type, semantic_type,
                   provider, source_url, storage_path,
                   language, published_at,
                   duration_seconds, file_size_bytes, checksum,
                   manifest_version)
                VALUES
                  (%s,%s,%s,
                   %s,%s,%s,
                   %s,%s,
                   %s,%s,%s,
                   %s)
                ON DUPLICATE KEY UPDATE
                  media_type=VALUES(media_type),
                  semantic_type=VALUES(semantic_type),
                  provider=VALUES(provider),
                  source_url=VALUES(source_url),
                  language=VALUES(language),
                  published_at=VALUES(published_at),
                  duration_seconds=VALUES(duration_seconds),
                  file_size_bytes=VALUES(file_size_bytes),
                  checksum=VALUES(checksum),
                  manifest_version=VALUES(manifest_version),
                  id=LAST_INSERT_ID(id)
                """,
                media.to_insert_params(),
            )

            safe_execute_dict(cur, "SELECT LAST_INSERT_ID() AS id")
            rid = cur.fetchone()

            conn.commit()

            if rid and rid["id"]:
                mid = int(rid["id"])
                logger.debug(
                    "[MEDIAS] upsert note_id=%s storage=%s -> id=%s",
                    media.note_id,
                    media.storage_path,
                    mid,
                )
                return mid

            raise BrainOpsError(
                "Upsert Media KO",
                code=ErrCode.DB,
                ctx={"media": media},
            )

    except Exception as exc:
        conn.rollback()
        raise BrainOpsError(
            "Upsert Media KO",
            code=ErrCode.DB,
            ctx={"media": media},
        ) from exc

    finally:
        conn.close()


def get_media_by_id(media_id: int, *, logger: LoggerProtocol | None = None) -> Media | None:
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                "SELECT * FROM medias WHERE id = %s",
                (media_id,),
                logger=logger,
            )
            row = cur.fetchone()
        if row:
            return Media.from_row(row)
        return None
    finally:
        conn.close()
