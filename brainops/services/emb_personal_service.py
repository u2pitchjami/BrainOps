"""
Services de réconciliation liés aux notes personnelles.
"""

from pathlib import Path
from typing import Any

from brainops.models.event import QueueTask
from brainops.process_folders.detect_folder_type import (
    PERSONAL_DOCUMENT_TYPES,
)
from brainops.sql.db_connection import (
    get_db_connection,
    get_dict_cursor,
)
from brainops.sql.db_utils import safe_execute_dict
from brainops.sql.notes.db_notes_utils import get_note_by_id
from brainops.utils.logger import LoggerProtocol


def get_personal_ids_for_embedding(
    *,
    limit: int = 100,
    logger: LoggerProtocol | None = None,
) -> list[int]:
    """
    Retourne les identifiants des notes personnelles à contrôler.

    Les notes sélectionnées ont été mises à jour depuis plus d'une heure, mais depuis moins de six heures.
    """
    if limit <= 0:
        raise ValueError("limit doit être strictement supérieur à zéro")

    placeholders = ", ".join(["%s"] * len(PERSONAL_DOCUMENT_TYPES))

    params: tuple[object, ...] = (
        *(doc_type.value for doc_type in PERSONAL_DOCUMENT_TYPES),
        limit,
    )

    conn = get_db_connection(logger=logger)

    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                f"""
                SELECT id
                FROM obsidian_notes
                WHERE updated_at <= NOW() - INTERVAL 1 HOUR
                  AND updated_at > NOW() - INTERVAL 6 HOUR
                  AND doc_type IN ({placeholders})
                ORDER BY updated_at ASC
                LIMIT %s
                """,
                params,
            )

            rows: list[dict[str, Any]] = cur.fetchall() or []

    except Exception:
        if logger is not None:
            logger.exception(
                "[RECONCILE-PERSONAL] Impossible de sélectionner\
                             les notes pour le contrôle des embeddings"
            )
        raise

    finally:
        conn.close()

    note_ids: list[int] = []

    for row in rows:
        raw_id = row.get("id")

        if not isinstance(raw_id, int):
            if logger is not None:
                logger.warning(
                    "[RECONCILE-PERSONAL] ID de note invalide ignoré : %r",
                    raw_id,
                )
            continue

        note_ids.append(raw_id)

    return note_ids


def personal_embeddings(
    logger: LoggerProtocol,
    *,
    limit: int = 100,
) -> None:
    """
    Met en file les notes personnelles éligibles aux embeddings.

    Le module d'embedding décide lui-même si un recalcul est nécessaire, selon l'existence des embeddings et la
    correspondance du hash.
    """
    try:
        note_ids = get_personal_ids_for_embedding(
            limit=limit,
            logger=logger,
        )
    except Exception:
        logger.exception("[RECONCILE-PERSONAL] Contrôle des embeddings annulé : sélection des notes impossible")
        return

    if not note_ids:
        logger.info("[RECONCILE-PERSONAL] Aucune note éligible au contrôle des embeddings")
        return

    logger.info(
        "[RECONCILE-PERSONAL] Contrôle des embeddings pour %d note(s)",
        len(note_ids),
    )

    # Import local conservé si nécessaire pour éviter une dépendance circulaire.
    from brainops.watcher.queue_manager import enqueue_event

    queued_count = 0

    for note_id in note_ids:
        try:
            note_db = get_note_by_id(note_id, logger=logger)

            if note_db is None or note_db.id is None:
                logger.warning(
                    "[RECONCILE-PERSONAL] Note non trouvée en BDD : id=%s",
                    note_id,
                )
                continue

            file_path = Path(note_db.file_path)
            if not file_path.is_file():
                logger.warning(
                    "[RECONCILE-PERSONAL] Fichier absent pour la note id=%s : %s",
                    note_id,
                    file_path,
                )
                continue

            enqueue_event(
                {
                    "type": "file",
                    "path": str(file_path),
                    "action": "modified",
                    "Note": note_db,
                    "task": QueueTask.CHECK_EMBEDDING,
                }
            )

            queued_count += 1

            logger.info(
                "[RECONCILE-PERSONAL] Note id=%s mise en file pour contrôle des embeddings",
                note_db.id,
            )

        except Exception:
            logger.exception(
                "[RECONCILE-PERSONAL] Erreur pendant la mise en file du contrôle d'embedding : id=%s",
                note_id,
            )

    logger.info(
        "[RECONCILE-PERSONAL] %d/%d note(s) mise(s) en file pour contrôle des embeddings",
        queued_count,
        len(note_ids),
    )
