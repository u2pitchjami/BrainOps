"""
sql/db_temp_blocs.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymysql

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.utils.logger import LoggerProtocol, ensure_logger


@dataclass(frozen=True, slots=True)
class ExistingTempBlock:
    block_id: int
    response: str | None
    status: str


def get_existing_bloc(
    *,
    note_id: int | None = None,
    media_id: int | None = None,
    block_index: int,
    prompt: str,
    model: str,
    split_method: str,
    word_limit: int,
    source: str,
    content_hash: str,
    logger: LoggerProtocol | None = None,
) -> ExistingTempBlock | None:
    """
    Retourne le bloc temporaire correspondant exactement aux critères.

    Les comparaisons sur note_id et media_id utilisent l'opérateur null-safe de MariaDB.

    Le hash garantit que le bloc retrouvé correspond au contenu actuel.
    """
    current_logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=current_logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                """
                SELECT
                    id,
                    response,
                    status
                FROM obsidian_temp_blocks
                WHERE note_id <=> %s
                  AND media_id <=> %s
                  AND block_index = %s
                  AND prompt = %s
                  AND model_ollama = %s
                  AND split_method = %s
                  AND word_limit = %s
                  AND source = %s
                  AND content_hash = %s
                LIMIT 1
                """,
                (
                    note_id,
                    media_id,
                    block_index,
                    prompt,
                    model,
                    split_method,
                    word_limit,
                    source,
                    content_hash,
                ),
            )

            row = cur.fetchone()

            if row is None:
                return None

            return ExistingTempBlock(block_id=int(row["id"]), response=row["response"], status=str(row["status"]))

    except Exception as exc:
        current_logger.exception(
            "Erreur get_existing_bloc : note_id=%s media_id=%s block_index=%s source=%s content_hash=%s",
            note_id,
            media_id,
            block_index,
            source,
            content_hash,
        )
        raise BrainOpsError(
            "Lecture du bloc temporaire impossible",
            code=ErrCode.DB,
            ctx={
                "note_id": note_id,
                "media_id": media_id,
                "block_index": block_index,
                "source": source,
                "content_hash": content_hash,
            },
        ) from exc

    finally:
        conn.close()


def insert_bloc(
    *,
    note_id: int | None = None,
    media_id: int | None = None,
    block_index: int,
    content: str,
    prompt: str,
    model: str,
    split_method: str,
    word_limit: int,
    source: str,
    content_hash: str,
    logger: LoggerProtocol | None = None,
) -> int:
    """
    Insère un bloc temporaire avec le statut ``waiting``.

    Returns:
        Identifiant technique du bloc créé.

    Raises:
        BrainOpsError: si l'insertion échoue ou si aucun identifiant
        n'est retourné par MariaDB.
    """
    current_logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=current_logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                """
                INSERT INTO obsidian_temp_blocks (
                    note_id,
                    media_id,
                    block_index,
                    content,
                    prompt,
                    model_ollama,
                    split_method,
                    word_limit,
                    source,
                    content_hash,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'waiting')
                """,
                (
                    note_id,
                    media_id,
                    block_index,
                    content,
                    prompt,
                    model,
                    split_method,
                    word_limit,
                    source,
                    content_hash,
                ),
            )

            block_id = cur.lastrowid

            if block_id is None:
                raise BrainOpsError(
                    "Aucun identifiant retourné après insertion du bloc",
                    code=ErrCode.DB,
                    ctx={
                        "note_id": note_id,
                        "media_id": media_id,
                        "block_index": block_index,
                    },
                )

        conn.commit()

        current_logger.debug(
            "Bloc temporaire créé : block_id=%s note_id=%s media_id=%s block_index=%s source=%s",
            block_id,
            note_id,
            media_id,
            block_index,
            source,
        )

        return int(block_id)

    except BrainOpsError:
        conn.rollback()
        raise

    except pymysql.IntegrityError as exc:
        conn.rollback()
        raise BrainOpsError(
            "Contrainte d'intégrité lors de l'insertion du bloc",
            code=ErrCode.DB,
            ctx={
                "note_id": note_id,
                "media_id": media_id,
                "block_index": block_index,
                "source": source,
            },
        ) from exc

    except pymysql.MySQLError as exc:
        conn.rollback()
        current_logger.exception(
            "Erreur SQL lors de l'insertion du bloc : note_id=%s media_id=%s block_index=%s",
            note_id,
            media_id,
            block_index,
        )
        raise BrainOpsError(
            "Insert Temp_bloc KO",
            code=ErrCode.DB,
            ctx={
                "note_id": note_id,
                "media_id": media_id,
                "block_index": block_index,
            },
        ) from exc

    finally:
        conn.close()


def update_bloc_response(
    *,
    block_id: int,
    response: str,
    status: str = "processed",
    logger: LoggerProtocol | None = None,
) -> None:
    """
    Met à jour la réponse et le statut d'un bloc temporaire par son ID.
    """
    current_logger = ensure_logger(logger, __name__)
    conn = get_db_connection(logger=current_logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                """
                UPDATE obsidian_temp_blocks
                SET response = %s,
                    status = %s
                WHERE id = %s
                """,
                (
                    response.strip(),
                    status,
                    block_id,
                ),
            )

            if cur.rowcount != 1:
                raise BrainOpsError(
                    "Bloc temporaire introuvable ou mise à jour ambiguë",
                    code=ErrCode.DB,
                    ctx={
                        "block_id": block_id,
                        "rowcount": cur.rowcount,
                        "status": status,
                    },
                )

        conn.commit()

        current_logger.debug(
            "Bloc temporaire mis à jour : block_id=%s status=%s",
            block_id,
            status,
        )

    except BrainOpsError:
        conn.rollback()
        raise

    except Exception as exc:
        conn.rollback()
        current_logger.exception(
            "Erreur lors de la mise à jour du bloc : block_id=%s",
            block_id,
        )
        raise BrainOpsError(
            "update_bloc_response KO",
            code=ErrCode.DB,
            ctx={
                "block_id": block_id,
                "status": status,
            },
        ) from exc

    finally:
        conn.close()
