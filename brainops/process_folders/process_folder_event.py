"""
# handlers/start/process_folder_event.py
"""

from __future__ import annotations

from brainops.models.event import DirEvent
from brainops.models.folders import FolderType
from brainops.process_folders.detect_folder_type import detect_folder_type
from brainops.process_folders.folders import add_folder, update_folder
from brainops.sql.folders.db_folder_utils import exist_vault_db
from brainops.sql.folders.db_folders import delete_folder_from_db
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger
from brainops.utils.normalization import normalize_full_path


# ----- Hub ----------------------------------------------------------------------
@with_child_logger
def process_folder_event(event: DirEvent, logger: LoggerProtocol | None = None) -> None:
    """
    Gère un événement de dossier.

    Contrat recommandé :
      - created:  {"type":"directory","action":"created","path":<dst>}
      - deleted:  {"type":"directory","action":"deleted","path":<target>}
      - moved:    {"type":"directory","action":"moved","src_path":<src>,"path":<dst>}

    Compatibilité legacy :
      - moved peut aussi arriver avec new_path (ancien code).
    """
    logger = ensure_logger(logger, __name__)
    raw_path = event["path"]
    folder_path = normalize_full_path(raw_path)
    action = event["action"]
    logger.debug("[FOLDERS] event=%s path=%s", action, folder_path)

    # ignore dossiers cachés / non pertinents
    if folder_path.startswith(".") or "untitled" in folder_path.lower() or "sans titre" in folder_path.lower():
        logger.info(f"[INFO] Dossier ignoré : {folder_path}")
        return  # Ignore les dossiers cachés ou non pertinents

    if action == "created":
        ftype = detect_folder_type(folder_path)
        logger.info("[FOLDERS] add_folder(%s, type=%s)", folder_path, ftype)
        if ftype is FolderType.STORAGE:
            add_folder(folder_path, logger=logger)
        else:
            logger.info("[FOLDERS] Dossier ignoré (type=%s) : %s", ftype, folder_path)
        return

    if action == "deleted":
        logger.info("[FOLDERS] delete_folder_from_db (%s)", folder_path)
        delete_folder_from_db(folder_path, logger=logger)
        return

    if action == "moved":
        # format recommandé: src_path + path
        src = event.get("src_path")
        # compat ancien format: new_path
        dst = folder_path
        legacy_new = event.get("new_path")

        if src and dst:
            if src.startswith(".") or "untitled" in src.lower() or "sans titre" in src.lower():
                folder_type = detect_folder_type(dst)
                add_folder(dst, logger=logger)
                logger.info("[FOLDERS] add_folder(%s, type=%s)", dst, folder_type)
                return
            if not exist_vault_db(src, logger=logger):
                folder_type = detect_folder_type(dst)
                add_folder(dst, logger=logger)
                logger.info("[FOLDERS] add_folder(%s, type=%s)", dst, folder_type)
                return

            logger.info("[FOLDERS] update_folder(src=%s, dst=%s)", src, dst)
            update_folder(normalize_full_path(src), dst, logger=logger)
            return

        if legacy_new:
            new_dst = normalize_full_path(str(legacy_new))
            logger.info(
                "[FOLDERS] legacy moved: update_folder(src=%s, dst=%s)",
                folder_path,
                new_dst,
            )
            update_folder(folder_path, new_dst, logger=logger)
            return

        # Fallback (si on ne connaît pas la source) : add puis (éventuellement) delete via autre event
        ftype = detect_folder_type(dst)
        logger.info("[FOLDERS] moved sans src → add_folder(%s, %s)", dst, ftype)
        add_folder(dst, logger=logger)
        return

    # action inconnue
    logger.warning("[FOLDERS] action non gérée: %s", action)
