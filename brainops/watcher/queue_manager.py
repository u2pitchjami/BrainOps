"""
queue.
"""

# watcher/queue_manager.py
from __future__ import annotations

from pathlib import Path
from queue import Queue

from brainops.ingest.audio_pipeline import process_audio_manifests
from brainops.io.paths import exists
from brainops.models.event import DirEvent, Event, QueuedNoteContext
from brainops.models.exceptions import BrainOpsError
from brainops.models.note import Note
from brainops.models.note_context import NoteContext
from brainops.process_folders.process_folder_event import process_folder_event
from brainops.process_notes.check_duplicate import hub_check_duplicate
from brainops.process_notes.new_note import new_note
from brainops.process_notes.process_single_note import process_single_note
from brainops.process_notes.update_note import update_note_context
from brainops.scripts.run_auto_reconcile import run_reconcile_scripts
from brainops.sql.notes.db_delete_note import delete_note_by_path
from brainops.sql.notes.db_notes_utils import file_path_exists_in_db, get_note_by_id, get_note_by_path
from brainops.utils.files import wait_for_file
from brainops.utils.logger import get_logger
from brainops.watcher.queue_utils import PendingNoteLockManager, get_lock_key

logger = get_logger("Brainops Watcher")

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
    note_db: Note | None = None
    key: str | None = None
    if event["type"] == "file":
        file_path: str = event["path"]  # always present (TypedDict total)
        src_path: str | None = event.get("src_path")

        note_db = get_note_by_path(file_path, src_path, logger=logger)
        event["Note"] = note_db
        note = event.get("Note")
        logger.debug("[QUEUE] Enfile : %s", note)
        if note:
            note_id = note.id
        else:
            note_id = None
        logger.debug("[QUEUE] note_id : %s", note_id)
        key = get_lock_key(note_id, file_path)
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
        src_path: str | None = None
        locked: bool = False

        try:
            queued_ctx = event_queue.get()
            event = queued_ctx.event
            trigger_new = False
            logger.debug("[DEBUG] ===== PROCESS QUEUE EVENT RECUP : %s", event)
            file_path = event["path"]
            src_path = event.get("src_path")
            note_db = event.get("Note")
            etype = event["type"]
            action = event["action"]

            # Fichiers: attendre la présence (sauf 'deleted')
            if etype == "file":
                logger.debug("etype == file")

                if action != "deleted":
                    if not wait_for_file(file_path, logger=logger):
                        logger.warning("⚠️ Fichier introuvable, skip : %s", file_path)
                        continue  # passe à l'événement suivant

                # Assure un note_id si absent
                if note_db is None:
                    logger.debug("note_db is None")
                    if not exists(file_path):
                        continue
                note_id = file_path_exists_in_db(file_path, src_path, logger=logger)
                logger.debug("note_id file_path_exists_in_db : %s", note_id)
                if not note_id:
                    try:
                        # logger.debug("[DEBUG] ===== Test Title")
                        # test_title(file_path, logger=logger)
                        note_id = new_note(file_path, logger=logger)
                        logger.debug("note_id new_note : %s", note_id)

                        trigger_new = True
                    except BrainOpsError as exc:
                        logger.exception("[%s] %s | ctx=%r", exc.code, str(exc), exc.ctx)

                    logger.info("[INFO] Note créée : (id=%s) %s", note_id, file_path)
                if note_id:
                    if action == "deleted":
                        deleted = delete_note_by_path(file_path, logger=logger)
                        if deleted:
                            logger.info("[SUPPR] ✅ Note Supprimée: (id=%s) %s", note_id, file_path)
                        else:
                            logger.warning("[SUPPR] ❌ Rien à supprimer pour: %s", file_path)

                    if not note_db:
                        note_db = get_note_by_id(note_id, logger=logger)
                        if not note_db:
                            logger.warning("[WARN] ❌ Note non trouvée: (id=%s) %s", note_id, file_path)
                            continue
                    ctx = NoteContext(note_db=note_db, file_path=file_path, src_path=src_path, logger=logger)
                    logger.debug("[DEBUG] NoteContext créé: (id=%s) ctx: %s", note_id, ctx)
                    if (
                        ctx.note_db.title is None
                        or ctx.note_db.title.strip() == ""
                        or ctx.note_db.title.strip().lower() == "untitled"
                    ):
                        logger.debug(
                            "[DEBUG] Titre vide ou None, mise à jour du titre basé sur le nom de fichier: %s",
                            Path(file_path).stem,
                        )
                        ctx.note_db.title = Path(file_path).stem
                    update_note_context(ctx)
                    logger.debug("[DEBUG] Note créée: (id=%s) ctx: %s", note_id, ctx)

                    # Pose le lock si pas encore fait par enqueue_event
                    key = get_lock_key(note_db.id, file_path)
                    if lock_mgr.acquire(key):
                        locked = True

                    if trigger_new:
                        dup = hub_check_duplicate(ctx=ctx, logger=logger)
                        if dup:
                            logger.warning("[DUP] ❌ Note Dupliquée: (id=%s) %s", note_id, file_path)
                            continue

                    # created / modified / moved
                    if action in ("created", "modified"):
                        process_single_note(ctx, queued_ctx, logger=logger)

                    if action == "moved":
                        logger.debug("[BUSY] Déplacement fichier : %s -> %s", src_path, file_path)
                        process_single_note(ctx, queued_ctx, logger=logger)

            # Dossiers: déléguer au gestionnaire de dossiers
            if etype == "directory":
                if action == "moved":
                    dir_ev: DirEvent = {
                        "type": "directory",
                        "action": "moved",
                        "src_path": event["src_path"],
                        "path": event["path"],
                    }
                else:
                    dir_ev = {
                        "type": "directory",
                        "action": event["action"],
                        "path": event["path"],
                    }

                process_folder_event(dir_ev, logger=logger)

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
