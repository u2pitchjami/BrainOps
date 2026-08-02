from pathlib import Path

from brainops.models.event import QueueTask
from brainops.utils.config import IMPORTS_PATH
from brainops.utils.logger import LoggerProtocol, ensure_logger


def scan_import_directory(import_directory: Path = Path(IMPORTS_PATH), logger: LoggerProtocol | None = None) -> None:
    """
    Envoie à la file toutes les notes présentes dans le dossier imports.
    """
    logger = ensure_logger(logger, __name__)
    try:
        for file_path in import_directory.glob("*.md"):
            if not file_path.is_file():
                continue
            from brainops.watcher.queue_manager import enqueue_event

            enqueue_event(
                {
                    "type": "file",
                    "path": str(file_path),
                    "action": "reconcile",
                    "task": QueueTask.IMPORT,
                }
            )
            logger.info("Mise en file d'attente de la note %s pour importation", file_path)
    except OSError:
        logger.exception(
            "Erreur pendant le scan du dossier imports: %s",
            import_directory,
        )
