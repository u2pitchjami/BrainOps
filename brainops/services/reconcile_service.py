# brainops/services/reconcile_service.py

from collections.abc import Iterable
import os
from pathlib import Path
from typing import cast

from brainops.io.paths import to_abs, to_rel
from brainops.models.config import get_check_config
from brainops.models.reconcile import ApplyStats, CheckConfig, DiffSets, FolderRow
from brainops.process_folders.folders import add_folder
from brainops.process_notes.new_note import new_note
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.sql.folders.db_folders import delete_folder_from_db
from brainops.sql.notes.db_delete_note import delete_note_by_path
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def _iter_physical_dirs(base: Path, logger: LoggerProtocol | None = None) -> Iterable[Path]:
    logger = ensure_logger(logger, __name__)
    root = Path(to_abs(base))
    logger.debug("Scanning physical dirs under: %s", root)
    for dirpath, _, _ in os.walk(root):
        current_dir = Path(dirpath)
        # logger.debug("Found directory: %s", current_dir)
        try:
            if current_dir.is_dir() and not _is_hidden_path(current_dir) and current_dir != root:
                # logger.debug("Yielding directory: %s", Path(to_rel(current_dir)))
                yield Path(to_rel(current_dir))
        except Exception:  # pylint: disable=broad-except
            continue


def _iter_md_files(base_path: Path) -> Iterable[Path]:
    root = Path(to_abs(base_path)).resolve()
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".md") and not filename.startswith("~"):
                full_path = Path(dirpath) / filename
                if not _is_hidden_path(full_path):
                    yield Path(to_rel(full_path))


def _is_hidden_path(p: Path) -> bool:
    return any(part.startswith(".") for part in Path(to_abs(p)).parts)


@with_child_logger
def collect_diffs(cfg: CheckConfig, logger: LoggerProtocol | None = None) -> DiffSets:
    logger = ensure_logger(logger, __name__)
    logger.info("=== COLLECTE DES ÉCARTS ===")
    errors_rows: list[tuple[str, str]] = []

    conn = get_db_connection(logger=logger)
    try:
        # --- Folders
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(cur, "SELECT id, path, folder_type, category_id, subcategory_id FROM obsidian_folders")
            db_folders = cast(list[FolderRow], list(cur.fetchall()))

        Path(cfg.base_path)
        physical_dirs: set[Path] = set(_iter_physical_dirs(cfg.base_path, logger=logger))
        logger.debug("physical_dirs: %s", physical_dirs)
        # physical_dirs.add(base_notes)
        db_folder_paths = {Path(row["path"]) for row in db_folders}
        logger.debug("db_folder_paths: %s", db_folder_paths)
        folders_missing_in_db = sorted(str(p) for p in (physical_dirs - db_folder_paths))
        folders_ghost_in_db = sorted(str(p) for p in (db_folder_paths - physical_dirs))
        if "." in folders_ghost_in_db:
            folders_ghost_in_db.remove(".")
        logger.debug("folders_ghost_in_db: %s", folders_ghost_in_db)

        for p in folders_missing_in_db:
            if (
                p == "."
                or p == "./"
                or p == ""
                or p == "/"
                or p == "\\"
                or p == "/app"
                or p == "/app/notes"
                or p == "/app/audio"
            ):
                continue
            logger.info("📁 + Dossier à ajouter (DB) : %s", p)
            errors_rows.append(("folder_missing_in_db", p))
        for p in folders_ghost_in_db:
            if (
                p == "."
                or p == "./"
                or p == ""
                or p == "/"
                or p == "\\"
                or p == "/app"
                or p == "/app/notes"
                or p == "/app/audio"
            ):
                continue
            logger.info("📁 - Dossier à supprimer (DB) : %s", p)
            errors_rows.append(("folder_ghost_in_db", p))

        # --- Notes
        with get_dict_cursor(conn) as cur:
            safe_execute_dict(cur, "SELECT id, file_path FROM obsidian_notes")
            notes_rows = cur.fetchall() or []

        notes_missing_file: list[str] = []
        for note in notes_rows:
            fpath = Path(str(note["file_path"]))
            try:
                fpath_res = to_abs(fpath)
                if not Path(to_abs(fpath_res)).is_file():
                    notes_missing_file.append(str(fpath))
                    errors_rows.append(("note_missing_file", str(fpath)))
                    logger.info("📝 - Note fantôme en DB (fichier absent) : %s", fpath_res)
            except Exception:  # pylint: disable=broad-except  # pragma: no cover
                notes_missing_file.append(str(fpath))
                errors_rows.append(("note_missing_file", str(fpath)))
                logger.info("📝 - Note fantôme en DB (chemin non résolu) : %s", fpath)

        all_md_files: set[Path] = set(_iter_md_files(cfg.base_notes))
        db_note_paths = {Path(str(n["file_path"])) for n in notes_rows}
        db_note_paths_resolved = {p for p in db_note_paths if to_abs(p).exists()}
        notes_missing_in_db = sorted(str(p) for p in (all_md_files - db_note_paths_resolved))
        for p in notes_missing_in_db:
            errors_rows.append(("note_missing_in_db", p))
            logger.info("📝 + Note à ajouter (DB) : %s", p)

        if len(errors_rows) == 0:
            logger.info("✅ - Aucune erreur détectée")

        return DiffSets(
            folders_missing_in_db=folders_missing_in_db,
            folders_ghost_in_db=folders_ghost_in_db,
            notes_missing_in_db=notes_missing_in_db,
            notes_missing_file=notes_missing_file,
        )
    finally:
        try:
            conn.close()
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            logger.warning("DB connection close failed", exc_info=True)


@with_child_logger
def apply_diffs(diffs: DiffSets, cfg: CheckConfig, logger: LoggerProtocol | None = None) -> ApplyStats:
    logger = ensure_logger(logger, __name__)
    stats = ApplyStats()

    # --- FOLDERS À AJOUTER ---
    for folder_path in diffs.folders_missing_in_db:
        try:
            folder_id = add_folder(folder_path)
            stats.added_folders += 1
            logger.info("✅ Ajout dossier : %s (id=%s)", folder_path, folder_id)
        except Exception as e:
            stats.errors += 1
            logger.warning("❌ Erreur ajout dossier : %s (%s)", folder_path, e)

    # --- FOLDERS À SUPPRIMER ---
    for folder_path in diffs.folders_ghost_in_db:
        try:
            deleted = delete_folder_from_db(folder_path)
            stats.deleted_folders += deleted
            logger.info("🗑️ Suppression dossier : %s", folder_path)
        except Exception as e:
            stats.errors += 1
            logger.warning("❌ Erreur suppression dossier : %s (%s)", folder_path, e)

    # --- NOTES À AJOUTER ---
    for note_path in diffs.notes_missing_in_db:
        try:
            note_id = new_note(note_path)
            stats.added_notes += 1
            logger.info("✅ Ajout note : %s (id=%s)", note_path, note_id)
        except Exception as e:
            stats.errors += 1
            logger.warning("❌ Erreur ajout note : %s (%s)", note_path, e)

    # --- NOTES À SUPPRIMER ---
    for note_path in diffs.notes_missing_file:
        try:
            deleted = delete_note_by_path(note_path)
            stats.deleted_notes += deleted
            logger.info("🗑️ Suppression note : %s", note_path)
        except Exception as e:
            stats.errors += 1
            logger.warning("❌ Erreur suppression note : %s (%s)", note_path, e)

    # --- Résumé ---
    logger.info("=== Résumé des actions ===")
    logger.info("🆕 Dossiers ajoutés : %d", stats.added_folders)
    logger.info("🗑️  Dossiers supprimés : %d", stats.deleted_folders)
    logger.info("🆕 Notes ajoutées : %d", stats.added_notes)
    logger.info("🗑️  Notes supprimées : %d", stats.deleted_notes)
    logger.info("⚠️  Erreurs : %d", stats.errors)

    return stats


@with_child_logger
def reconcile(scope: str = "all", apply: bool = False, logger: LoggerProtocol | None = None) -> None:
    """
    Point d'entrée principal.
    """
    logger = ensure_logger(logger, __name__)
    cfg = get_check_config(scope)
    logger.debug("Reconcile config: %s", cfg)
    diffs = collect_diffs(cfg, logger=logger)
    logger.debug("Diffs collected: %s", diffs)
    if apply:
        apply_diffs(diffs, cfg, logger=logger)
