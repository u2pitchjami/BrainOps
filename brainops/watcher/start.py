"""
Start watcher.
"""

# /watcher/start.py
from __future__ import annotations

import os
import re
import threading
import time

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from brainops.io.paths import to_rel
from brainops.models.event import EventType
from brainops.utils.config import (
    BASE_NOTES,
    LOCK_PURGE,
    MAINTENANCE_TIMING,
    WATCHDOG_DEBOUNCE_WINDOW,
    WATCHDOG_POLL_INTERVAL,
)
from brainops.utils.logger import LoggerProtocol, ensure_logger
from brainops.utils.normalization import normalize_full_path
from brainops.watcher.queue_manager import (
    enqueue_event,
    get_logger,
    log_event_queue,
    process_queue,
)
from brainops.watcher.queue_utils import PendingNoteLockManager

logger = get_logger("Brainops Watcher")

_TEMP_NAME_RE = re.compile(
    r"""^(
        untitled
      | sans[\s_-]*titre
      | new[\s_-]*note
      | nouvelle[\s_-]*note
      | new[\s_-]*folder
      | nouveau[\s_-]*dossier
    )(?:[\s_-]*\d+|\s*\(\d+\))?$""",
    re.IGNORECASE | re.VERBOSE,
)

LOCK_MGR = PendingNoteLockManager()


def _start_queue_thread() -> threading.Thread:
    """
    Lance process_queue() dans un thread daemon pour ne pas bloquer la boucle principale.
    """
    thread = threading.Thread(target=process_queue, name="queue-worker", daemon=True)
    thread.start()
    return thread


def start_watcher(*, logger: LoggerProtocol | None = None) -> None:
    """
    Démarre la surveillance du vault Obsidian (PollingObserver).

    Lit la config via .env :
      - BASE_NOTES (obligatoire, chemin existant)
      - WATCHDOG_POLL_INTERVAL (float, défaut 1.0)
      - WATCHDOG_DEBOUNCE_WINDOW (float, défaut 0.5)
    """
    logger = ensure_logger(logger, __name__)
    logger.info(
        "Watcher démarré (PollingObserver, interval=%.2fs) sur %s",
        WATCHDOG_POLL_INTERVAL,
        BASE_NOTES,
    )
    if os.environ.get("USE_POLLING", "0") == "1":
        print("🔁 [Watcher] Polling forcé via USE_POLLING=1")
        observer = PollingObserver(timeout=WATCHDOG_POLL_INTERVAL)
    else:
        # Cas normal (ex: dev local)
        print("👀 [Watcher] Observer natif activé")
        observer = Observer()

    handler = NoteHandler(logger=logger, debounce_window=WATCHDOG_DEBOUNCE_WINDOW)
    observer.schedule(handler, BASE_NOTES, recursive=True)
    observer.start()
    worker = _start_queue_thread()
    enqueue_event({"type": "script", "action": "reconcile", "path": "path"})
    enqueue_event({"type": "script", "action": "audio", "path": "path"})

    last_maintenance = time.monotonic()
    try:
        while True:
            time.sleep(0.5)
            now = time.monotonic()
            if now - last_maintenance >= MAINTENANCE_TIMING:
                logger.info("🪵 Etat Horaire")
                log_event_queue()
                locks = LOCK_MGR.get_all_locks()
                logger.info("🔒 Locks actifs : %d", len(locks))
                for key, ts in locks.items():
                    age = int(time.time() - ts)  # ts = epoch seconds
                    logger.info("  - %s | actif depuis %d s", key, age)
                logger.info("🧹 Purge des locks expirés (timeout=%d s)", LOCK_PURGE)
                LOCK_MGR.purge_expired(timeout=LOCK_PURGE)
                last_maintenance = now
                enqueue_event({"type": "script", "action": "reconcile", "path": "path"})
                enqueue_event({"type": "script", "action": "audio", "path": "path"})

    except KeyboardInterrupt:
        logger.info("Arrêt demandé (CTRL+C).")
    finally:
        observer.stop()
        observer.join(timeout=10)
        if worker.is_alive():
            logger.info("Arrêt du worker de queue…")
        logger.info("Watcher arrêté proprement.")


Pathish = str | bytes | os.PathLike[str] | os.PathLike[bytes]


class NoteHandler(FileSystemEventHandler):
    """
    Émet des payloads normalisés dans la queue à partir des événements FS.
    """

    def __init__(self, *, logger: LoggerProtocol | None, debounce_window: float) -> None:
        """
        Args:
            logger: Logger compatible LoggerProtocol, ou None.
            debounce_window: Fenêtre anti-rafale en secondes.
        """
        self._logger = logger
        # ⚠️ Utiliser bien le paramètre fourni (au lieu de WATCHDOG_DEBOUNCE_WINDOW)
        self._debounce_window = debounce_window  # #bug corrigé
        self._last_event: dict[tuple[str, str], float] = {}

    # ---- helpers ---------------------------------------------------------------

    @staticmethod
    def _to_str(path: Pathish) -> str:
        """
        Convertit str/bytes/PathLike en str (utf-8 avec surrogateescape).

        Toujours retourner une str pour unifier le traitement.
        """
        s = os.fspath(path)  # str | bytes
        if isinstance(s, bytes):
            # utf-8 + surrogateescape: évite les erreurs sur noms non-décodables
            return s.decode("utf-8", errors="surrogateescape")
        return s

    @staticmethod
    def _is_hidden_or_temp(path: Pathish) -> bool:
        """
        Retourne True si le chemin (fichier ou dossier) est caché ou temporaire.
        """
        s = NoteHandler._to_str(path)
        parts = s.split(os.sep)
        if any(p.startswith(".") for p in parts if p):  # .git, .obsidian, etc.
            return True
        basename = parts[-1] if parts else s
        return basename.endswith(("~", ".swp", ".tmp"))

    def _should_emit(self, path: Pathish, action: str, etype: str) -> bool:
        """Anti-rafale: évite les doublons dans une fenêtre courte."""
        s = self._to_str(path)
        key = (s, f"{action}:{etype}")
        now = time.monotonic()
        last = self._last_event.get(key, 0.0)
        if now - last < self._debounce_window:
            return False
        self._last_event[key] = now
        return True

    # ---- events ---------------------------------------------------------------

    def on_created(self, event: FileSystemEvent) -> None:
        """
        Traite la création de fichiers/dossiers.
        """
        if self._is_hidden_or_temp(event.src_path):
            return
        etype: EventType = "directory" if event.is_directory else "file"
        path = normalize_full_path(self._to_str(event.src_path))
        path_rel = to_rel(path)
        if self._should_emit(path_rel, "created", etype):
            if self._logger is not None:
                self._logger.info("[CREATION] %s → %s", etype.upper(), path_rel)
            enqueue_event({"type": etype, "action": "created", "path": path_rel})

    def on_deleted(self, event: FileSystemEvent) -> None:
        """
        Traite la suppression de fichiers/dossiers.
        """
        if self._is_hidden_or_temp(event.src_path):
            return
        etype: EventType = "directory" if event.is_directory else "file"
        path = normalize_full_path(self._to_str(event.src_path))
        path_rel = to_rel(path)
        if self._should_emit(path_rel, "deleted", etype):
            if self._logger is not None:
                self._logger.info("[SUPPRESSION] %s → %s", etype.upper(), path_rel)
            enqueue_event({"type": etype, "action": "deleted", "path": path_rel})

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        Traite les modifications de fichiers (ignore les dossiers).
        """
        if event.is_directory or self._is_hidden_or_temp(event.src_path):
            return
        etype: EventType = "file"
        path = normalize_full_path(self._to_str(event.src_path))
        path_rel = to_rel(path)
        if self._should_emit(path_rel, "modified", etype):
            if self._logger is not None:
                self._logger.info("[MODIFICATION] FILE → %s", path_rel)
            enqueue_event({"type": "file", "action": "modified", "path": path_rel})

    def on_moved(self, event: FileMovedEvent) -> None:
        """
        Traite les déplacements/renommages.
        """
        if self._is_hidden_or_temp(event.src_path) or self._is_hidden_or_temp(event.dest_path):
            return
        etype: EventType = "directory" if event.is_directory else "file"
        src = normalize_full_path(self._to_str(event.src_path))
        dst = normalize_full_path(self._to_str(event.dest_path))
        src_rel = to_rel(src)
        dst_rel = to_rel(dst)
        if self._should_emit(dst_rel, "moved", etype):
            if self._logger is not None:
                self._logger.info("[DEPLACEMENT] %s → %s -> %s", etype.upper(), src_rel, dst_rel)
            enqueue_event({"type": etype, "action": "moved", "src_path": src_rel, "path": dst_rel})
