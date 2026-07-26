"""
# handlers/process/move_error_file.py
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any

from brainops.io.paths import to_abs
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.process_folders.folders import ensure_folder_exists
from brainops.sql.get_linked.db_get_linked_notes_utils import get_data_for_should_trigger, get_file_path
from brainops.sql.notes.db_update_notes import update_obsidian_note
from brainops.utils.config import ERRORED_JSON, ERRORED_PATH
from brainops.utils.files import wait_for_file
from brainops.utils.logger import LoggerProtocol, ensure_logger


def _unique_dest(dest: Path) -> Path:
    if not Path(to_abs(str(dest))).exists():
        return dest
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return dest.with_name(f"{dest.stem}__{ts}{dest.suffix}")


def _exc_payload(exc: BrainOpsError | str | list[str]) -> dict[str, Any]:
    if isinstance(exc, BrainOpsError):
        return {
            "type": exc.__class__.__name__,
            "code": getattr(exc, "code", None),
            "msg": str(exc),
            "ctx": getattr(exc, "ctx", None),
        }
    if isinstance(exc, list):
        return {"error": "; ".join(exc)}
    if isinstance(exc, str):
        return {"error": exc}
    return {"error": "Unknown error"}


def handle_errored_file(
    note_id: int,
    filepath: str | Path,
    exc: BrainOpsError | list[str] | str,
    *,
    logger: LoggerProtocol | None = None,
) -> None:
    """
    Déplace la note (cas d’erreur) vers ERRORED_PATH, en protégeant la paire synthesis/archive : on conserve l’archive,
    on purge la synthèse si la paire existe.

    Si la synthèse est “solo”, on déplace la synthèse elle-même.
    """
    logger = ensure_logger(logger, __name__)
    src_for_log: Path = Path(filepath)
    try:
        ensure_folder_exists(Path(ERRORED_PATH), logger=logger)
        always = wait_for_file(file_path=filepath, logger=logger)
        if not always:
            logger.warning("[WARNING] 🚨 Note déjà supprimée")
            return
        status, parent_id, _ = get_data_for_should_trigger(note_id=note_id, logger=logger)
        # Casser la réciprocité si elle existe (évite suppression en chaîne)
        if parent_id:
            parent_filepath = get_file_path(note_id=parent_id, logger=logger)
            updates = {"parent_id": None}
            update_obsidian_note(note_id, updates, logger=logger)
            update_obsidian_note(parent_id, updates, logger=logger)
        else:
            parent_filepath = None

        # Déterminer src (fichier déplacé) et éventuellement path_to_delete (fichier à supprimer)
        if status == "synthesis":
            if parent_filepath:
                # Paire présente : on déplace l’archive et on supprime la synthèse
                src = Path(str(parent_filepath))
                path_to_delete = Path(str(filepath))
                def_note_id = parent_id  # l’archive devient la note “survivante”
            else:
                # Synthèse “solo” : on déplace la synthèse elle-même (pas d’autre action)
                src = Path(str(filepath))
                path_to_delete = None
                def_note_id = note_id
        else:
            # status == "archive" (ou autre inattendu : on traite comme archive)
            src = Path(str(filepath))
            path_to_delete = Path(str(parent_filepath)) if parent_filepath else None
            def_note_id = note_id

        src_for_log = src  # pour le except
        dest = _unique_dest(Path(ERRORED_PATH) / src.name)
        shutil.move(to_abs(src).as_posix(), to_abs(dest).as_posix())
        logger.warning("[WARNING] 🚨 Note déplacée vers 'error' : %s", dest.as_posix())

        # Sécurité : ne tente pas de supprimer le fichier qu’on vient de déplacer
        if path_to_delete and path_to_delete.exists() and path_to_delete != dest:
            try:
                os.remove(Path(to_abs(path_to_delete.as_posix())))
                logger.info("🗑️ [FILE] Fichier supprimé : %s", path_to_delete)
            except Exception as rm_exc:
                logger.warning("Suppression échouée (%s): %s", path_to_delete, rm_exc)

        # MAJ DB sur la note “survivante”
        if def_note_id:
            updates_folder = {"file_path": dest.as_posix(), "status": "error"}
            update_obsidian_note(def_note_id, updates_folder, logger=logger)

        # Journal JSON (payload sérialisable)
        payload = _exc_payload(exc) | {"note_id": note_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        data = {}
        if Path(ERRORED_JSON).exists():
            with open(ERRORED_JSON, encoding="utf-8") as f:
                data = json.load(f)
        data[dest.as_posix()] = payload
        with open(ERRORED_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    except Exception as inner_exc:
        logger.exception("[ERREUR] handle_errored_file(%s) : %s", src_for_log.as_posix(), inner_exc)
        raise BrainOpsError(
            "déplacement vers ERRORED_PATH KO", code=ErrCode.METADATA, ctx={"note_id": note_id}
        ) from inner_exc
