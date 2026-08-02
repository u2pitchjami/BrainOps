"""
queue.
"""

# watcher/queue_manager.py
from __future__ import annotations

from queue import Queue

from brainops.ingest.audio_pipeline import process_audio_manifests
from brainops.models.event import Event, QueuedNoteContext, QueueTask
from brainops.models.note import Note
from brainops.process_notes.process_single_note import process_single_note, process_single_note_outside_queue
from brainops.scripts.run_auto_reconcile import run_reconcile_scripts
from brainops.utils.logger import get_logger
from brainops.watcher.queue_utils import PendingNoteLockManager, get_lock_key

logger = get_logger("Brainops Queue")

# ---- Typage des événements -----------------------------------------------------

# File d’attente unique et lock manager
event_queue: Queue[QueuedNoteContext] = Queue()
lock_mgr = PendingNoteLockManager()


def replay_enqueue(qnc: QueuedNoteContext) -> None:
    """
    Release lock and re-enqueue event.
    """
    if qnc.lock_key is not None:
        lock_mgr.release(qnc.lock_key)

    enqueue_event(qnc.event)


def enqueue_event(event: Event) -> None:
    """
    Enrichit et enfile un événement.

    - Pour les fichiers, pose un lock logique (note_id ou path).
    - Si le lock existe déjà, l'événement est ignoré (dé-bounce de travail).
    """
    key: str | None = None
    note_db: Note | None = None
    file_path: str = event["path"]
    raw_task = event.get("task")
    task = QueueTask(raw_task) if raw_task is not None else None

    if event["type"] == "file":
        note_db = process_single_note_outside_queue(event=event)

        if not note_db:
            logger.error(f"Impossible de récupérer Note : {file_path}")
            return
        if not task:
            return
        else:
            key = get_lock_key(note_db.id, file_path)
            logger.debug("[QUEUE] key : %s", key)
            if not lock_mgr.acquire(key):
                logger.debug("[QUEUE] 🚫 Ignoré, déjà en file : %s", key)
                return
    queued_ctx = QueuedNoteContext(
        note=note_db,
        event=event,
        lock_key=key,
    )

    event_queue.put(queued_ctx)
    logger.debug("[QUEUE] Taille actuelle: %d", event_queue.qsize())
    log_event_queue()


def process_queue() -> None:
    """
    Boucle de consommation des événements.

    - Traite fichiers et dossiers.
    - Relâche toujours les locks en fin de traitement.
    """
    log_event_queue()
    while True:
        queued_ctx: QueuedNoteContext | None = None
        event: Event | None = None
        file_path: str | None = None
        locked: bool = False

        try:
            queued_ctx = event_queue.get()
            event = queued_ctx.event
            logger.debug("[DEBUG] ===== PROCESS QUEUE EVENT RECUP : %s", event)
            file_path = event["path"]
            note_db = event.get("Note")
            etype = event["type"]
            action = event["action"]
            note_id = note_db.id if note_db else None

            # ignore dossiers cachés / non pertinents
            if file_path.startswith(".") or "untitled" in file_path.lower() or "sans titre" in file_path.lower():
                logger.info(f"[enqueue_event] Fichier ignoré car sans titre : {file_path}")
                continue

            # Fichiers: attendre la présence (sauf 'deleted')
            if etype == "file":
                process_ok = process_single_note(queued_ctx)
                if process_ok:
                    logger.info("[enqueue_event] Traitement de la note %s OK", note_id)
                else:
                    logger.warning("[enqueue_event] Traitement de la note %s KO", note_id)

            if etype == "script":
                if action == "reconcile":
                    run_reconcile_scripts()
                if action == "audio":
                    process_audio_manifests()

            logger.debug("[DEBUG] Fini: %s - %s", etype, action)
            log_event_queue()

        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("[ERREUR] File d'attente: %s", exc)
        finally:
            # Release lock si un lock est posé pour les fichiers
            if (event is not None) and (event.get("type") == "file"):
                # On reconstruit la clé de manière robuste
                key = get_lock_key(note_id, file_path)
                if key and (locked or lock_mgr.is_locked(key)):
                    lock_mgr.release(key)
            event_queue.task_done()


def log_event_queue() -> None:
    """
    Logge un aperçu de la file en DEBUG.
    """
    try:
        items = list(event_queue.queue)
        logger.debug("[DEBUG] Contenu file d'attente : %s", items)
    except Exception:  # queue interne peut changer pendant l’itération
        logger.debug("[DEBUG] Contenu file d'attente : <non disponible>")
