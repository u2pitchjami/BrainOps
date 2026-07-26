"""
# sql/db_medias.py
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.media import Media
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import (
    LoggerProtocol,
    ensure_logger,
)


def upsert_media_from_model(
    media: Media,
    *,
    logger: LoggerProtocol | None = None,
) -> int:
    """
    Effectue un upsert idempotent par `(note_id, storage_path)`.

    Retourne l'identifiant du média inséré ou mis à jour grâce à `LAST_INSERT_ID(id)`.
    """
    logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                """
                INSERT INTO medias (
                    note_id,
                    media_type,
                    doc_type,
                    provider,
                    source_url,
                    storage_path,
                    language,
                    published_at,
                    duration_seconds,
                    file_size_bytes,
                    checksum,
                    manifest_version,
                    editorial_context
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    media_type = VALUES(media_type),
                    doc_type = VALUES(doc_type),
                    provider = VALUES(provider),
                    source_url = VALUES(source_url),
                    language = VALUES(language),
                    published_at = VALUES(published_at),
                    duration_seconds = VALUES(duration_seconds),
                    file_size_bytes = VALUES(file_size_bytes),
                    checksum = VALUES(checksum),
                    manifest_version = VALUES(manifest_version),
                    editorial_context = VALUES(editorial_context),
                    id = LAST_INSERT_ID(id)
                """,
                media.to_insert_params(),
                logger=logger,
            )

            safe_execute_dict(
                cur,
                "SELECT LAST_INSERT_ID() AS id",
                logger=logger,
            )
            result = cur.fetchone()

            if not result or not result.get("id"):
                raise BrainOpsError(
                    "Identifiant absent après l'upsert du média",
                    code=ErrCode.DB,
                    ctx={
                        "note_id": media.note_id,
                        "storage_path": media.storage_path,
                    },
                )

            media_id = int(result["id"])
            conn.commit()

            logger.debug(
                "[MEDIAS] upsert note_id=%s storage=%s doc_type=%s -> id=%s",
                media.note_id,
                media.storage_path,
                media.doc_type,
                media_id,
            )

            return media_id

    except BrainOpsError:
        try:
            conn.rollback()
        except Exception:
            logger.exception(
                "[MEDIAS] Échec du rollback pour note_id=%s",
                media.note_id,
            )
        raise

    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            logger.exception(
                "[MEDIAS] Échec du rollback pour note_id=%s",
                media.note_id,
            )

        raise BrainOpsError(
            "Upsert Media KO",
            code=ErrCode.DB,
            ctx={
                "note_id": media.note_id,
                "storage_path": media.storage_path,
                "doc_type": media.doc_type,
            },
        ) from exc

    finally:
        conn.close()


def get_media_by_id(
    media_id: int,
    *,
    logger: LoggerProtocol | None = None,
) -> Media | None:
    """
    Retourne un média à partir de son identifiant.
    """

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

    except Exception as exc:
        raise BrainOpsError(
            "Lecture Media KO",
            code=ErrCode.DB,
            ctx={"media_id": media_id},
        ) from exc

    finally:
        conn.close()
