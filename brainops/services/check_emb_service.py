# brainops/services/reconcile_service.py

import os
from pathlib import Path
from typing import Any

from brainops.models.event import QueueTask
from brainops.process_import.utils.paths import path_is_inside
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.sql.notes.db_notes_utils import get_note_by_id
from brainops.utils.config import IMPORTS_PATH
from brainops.utils.logger import LoggerProtocol


def get_random_note_ids_for_embedding_check(
    *,
    limit: int = 5,
    logger: LoggerProtocol | None = None,
) -> list[int]:
    """
    Retourne un échantillon aléatoire de notes non liées à un média.

    Les notes média sont exclues, car leurs embeddings portent sur le contenu du média et non sur le contenu de la note
    Obsidian.
    """
    if limit <= 0:
        raise ValueError("limit doit être strictement positif")

    conn = get_db_connection(logger=logger)
    try:
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(
                cur,
                "SELECT id FROM obsidian_notes\
                WHERE media_id IS NULL ORDER BY RAND() LIMIT %s",
                (limit,),
            )
            rows: list[dict[str, Any]] = cur.fetchall() or []

    except Exception:
        if logger is not None:
            logger.exception("[RECONCILE] Impossible de sélectionner les notes pour le contrôle des embeddings")
        raise

    finally:
        conn.close()

    note_ids: list[int] = []

    for row in rows:
        raw_id = row.get("id")

        if not isinstance(raw_id, int):
            if logger is not None:
                logger.warning(
                    "[RECONCILE] ID de note invalide ignoré : %r",
                    raw_id,
                )
            continue

        note_ids.append(raw_id)

    return note_ids


def reconcile_embeddings(
    *,
    sample_size: int = 5,
    logger: LoggerProtocol,
) -> None:
    """
    Contrôle un échantillon aléatoire de notes et déclenche leur flow d'embedding.

    Le module d'embedding décide lui-même si un recalcul est nécessaire selon l'existence des embeddings et la
    correspondance du hash.
    """
    try:
        note_ids = get_random_note_ids_for_embedding_check(
            limit=sample_size,
            logger=logger,
        )
    except Exception:
        logger.exception("[RECONCILE] Contrôle des embeddings annulé : sélection des notes impossible")
        return

    if not note_ids:
        logger.info("[RECONCILE] Aucune note éligible au contrôle des embeddings")
        return

    logger.info(
        "[RECONCILE] Contrôle des embeddings pour %d note(s)",
        len(note_ids),
    )

    for note_id in note_ids:
        try:
            note_db = get_note_by_id(note_id, logger=logger)

            if note_db is None or note_db.id is None:
                logger.warning(
                    "[RECONCILE] Note non trouvée en BDD : id=%s",
                    note_id,
                )
                continue

            file_path = Path(note_db.file_path)
            if path_is_inside(IMPORTS_PATH, os.path.dirname(file_path)):
                logger.info(
                    "[RECONCILE] Note %d en cours d'importation, skip",
                    (note_db.id),
                )
                continue

            from brainops.watcher.queue_manager import enqueue_event

            enqueue_event(
                {
                    "type": "file",
                    "path": str(file_path),
                    "action": "modified",
                    "Note": note_db,
                    "task": QueueTask.CHECK_EMBEDDING,
                }
            )
            logger.info("Mise en file d'attente de la note %s pour vérification embeddings", note_db.id)

        except FileNotFoundError:
            logger.warning(
                "[RECONCILE] Fichier absent pour la note id=%s",
                note_id,
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "[RECONCILE] Erreur inattendue pendant le contrôle d'embedding : id=%s",
                note_id,
            )
