"""
sql/db_temp_blocs.py.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

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
    Crée un bloc temporaire ou réinitialise un bloc existant.

    Un bloc existant correspondant à la contrainte unique est remis au
    statut ``waiting`` avec son nouveau contenu et son nouveau hash.

    Returns:
        Identifiant technique du bloc créé ou mis à jour.

    Raises:
        BrainOpsError: si l'opération échoue ou si aucun identifiant
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
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'waiting'
                )
                ON DUPLICATE KEY UPDATE
                    id = LAST_INSERT_ID(id),
                    content = VALUES(content),
                    prompt = VALUES(prompt),
                    split_method = VALUES(split_method),
                    word_limit = VALUES(word_limit),
                    content_hash = VALUES(content_hash),
                    status = 'waiting'
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

            if not isinstance(block_id, int) or block_id <= 0:
                raise BrainOpsError(
                    "Aucun identifiant retourné après création ou mise à jour du bloc",
                    code=ErrCode.DB,
                    ctx={
                        "note_id": note_id,
                        "media_id": media_id,
                        "block_index": block_index,
                    },
                )

        conn.commit()

        current_logger.debug(
            ("Bloc temporaire enregistré : block_id=%s note_id=%s media_id=%s block_index=%s source=%s"),
            block_id,
            note_id,
            media_id,
            block_index,
            source,
        )

        return block_id

    except BrainOpsError:
        conn.rollback()
        raise

    except pymysql.MySQLError as exc:
        conn.rollback()
        current_logger.exception(
            ("Erreur SQL lors de l'enregistrement du bloc : note_id=%s media_id=%s block_index=%s"),
            note_id,
            media_id,
            block_index,
        )
        raise BrainOpsError(
            "Enregistrement du bloc temporaire impossible",
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


def get_blocks(
    note_id: int | None,
    media_id: int | None,
    source: str = "embeddings",
    status: str = "processed",
    logger: LoggerProtocol | None = None,
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
                WHERE note_id <=> %s
                AND media_id <=> %s
                AND source = %s
                AND status = %s
                ORDER BY block_index
                """,
                (note_id, media_id, source, status),
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


def delete_blocks_from_index(
    *,
    note_id: int | None = None,
    media_id: int | None = None,
    source: str = "embeddings",
    status: str = "processed",
    first_index: int,
    logger: LoggerProtocol | None = None,
) -> None:
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
                DELETE FROM obsidian_temp_blocks
                    WHERE note_id <=> %s
                    AND media_id <=> %s
                    AND source = %s
                    AND status = %s
                    AND block_index >= %s;
                """,
                (note_id, media_id, source, status, first_index),
            )
            conn.commit()
            return

    except Exception as exc:
        current_logger.exception(
            "delete_blocks_from_index : note_id=%s media_id=%s source=%s status=%s first_index=%s",
            note_id,
            media_id,
            source,
            status,
            first_index,
        )
        raise BrainOpsError(
            "delete_blocks_from_index impossible",
            code=ErrCode.DB,
            ctx={
                "note_id": note_id,
                "media_id": media_id,
                "status": status,
                "source": source,
                "first_index": first_index,
            },
        ) from exc

    finally:
        conn.close()
