# brainops/services/reconcile_service.py

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime
import os
from pathlib import Path

from brainops.io.note_reader import read_metadata_object
from brainops.io.paths import to_abs, to_rel
from brainops.models.config import get_check_config
from brainops.models.metadata import NoteMetadata
from brainops.models.note import Note
from brainops.models.reconcile import ApplyStats, CheckConfig, DiffSets
from brainops.process_notes.new_note import new_note
from brainops.sql.db_connection import get_db_connection, get_dict_cursor
from brainops.sql.db_utils import safe_execute_dict
from brainops.sql.notes.db_delete_note import delete_note_by_path
from brainops.sql.notes.db_notes_utils import get_note_by_path
from brainops.sql.notes.db_update_notes import update_obsidian_note
from brainops.utils.logger import LoggerProtocol, ensure_logger


def detect_moves(
    diffs: DiffSets,
    *,
    logger: LoggerProtocol | None = None,
) -> DiffSets:
    """
    Détecte les notes déplacées entre les listes de suppression et de création.

    Une note est considérée comme déplacée si les critères d'identification correspondent de manière unique.

    Retourne un nouveau DiffSets avec les déplacements retirés.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("Détect Moves :")
    remaining_missing_db = list(diffs.notes_missing_in_db)
    remaining_missing_file = list(diffs.notes_missing_file)

    matched_db: set[str] = set()
    matched_file: set[str] = set()

    for old_path in diffs.notes_missing_file:
        note = get_note_by_path(old_path, logger=logger)
        if note is None or not note.id:
            continue

        candidates: list[str] = []

        for new_path in remaining_missing_db:
            metadata = read_metadata_object(new_path, logger=logger)
            if not metadata or not metadata.created:
                continue
            created = date.fromisoformat(metadata.created)
            logger.debug(
                "Comparaison déplacement:\n"
                "old_path=%s\n"
                "new_path=%s\n"
                "title: %r == %r\n"
                "created: %r (%s) == %r (%s)\n"
                "source: %r == %r\n"
                "filename: %r == %r",
                note.file_path,
                Path(new_path).stem,
                note.title,
                metadata.title,
                note.created_at,
                type(note.created_at).__name__,
                created,
                type(metadata.created).__name__,
                note.source,
                metadata.source,
                Path(note.file_path).name,
                Path(new_path).name,
            )

            if is_same_note(note, metadata, Path(new_path)):
                candidates.append(new_path)

        if len(candidates) != 1:
            if len(candidates) > 1:
                logger.warning(
                    "Déplacement ambigu pour %s (%d candidats)",
                    old_path,
                    len(candidates),
                )
            continue

        new_path = candidates[0]

        logger.info(
            "📂 Déplacement détecté : %s -> %s",
            old_path,
            new_path,
        )

        modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = {"file_path": new_path, "modified_at": modified_at}
        update = update_obsidian_note(note.id, updates, logger=logger)
        if not update:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement en base (id=%s)",
                note.id,
            )

        matched_file.add(old_path)
        matched_db.add(new_path)

    return replace(
        diffs,
        notes_missing_in_db=[p for p in remaining_missing_db if p not in matched_db],
        notes_missing_file=[p for p in remaining_missing_file if p not in matched_file],
    )


def is_same_note(note: Note, metadata: NoteMetadata, new_path: Path) -> bool:
    if not note or not metadata or not metadata.created:
        return False
    created = date.fromisoformat(metadata.created)
    return (
        metadata.title == note.title
        and created == note.created_at
        and metadata.source == (note.source or "")
        and Path(note.file_path).stem == Path(new_path).stem
    )


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


def collect_diffs(cfg: CheckConfig, logger: LoggerProtocol | None = None) -> DiffSets:
    logger = ensure_logger(logger, __name__)
    logger.info("=== COLLECTE DES ÉCARTS ===")
    errors_rows: list[tuple[str, str]] = []

    conn = get_db_connection(logger=logger)
    try:
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
            notes_missing_in_db=notes_missing_in_db,
            notes_missing_file=notes_missing_file,
        )
    finally:
        try:
            conn.close()
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            logger.warning("DB connection close failed", exc_info=True)


def apply_diffs(diffs: DiffSets, cfg: CheckConfig, logger: LoggerProtocol | None = None) -> ApplyStats:
    logger = ensure_logger(logger, __name__)
    stats = ApplyStats()

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
    logger.info("🆕 Notes ajoutées : %d", stats.added_notes)
    logger.info("🗑️  Notes supprimées : %d", stats.deleted_notes)
    logger.info("⚠️  Erreurs : %d", stats.errors)

    return stats


def reconcile(scope: str = "all", apply: bool = False, logger: LoggerProtocol | None = None) -> None:
    """
    Point d'entrée principal.
    """
    logger = ensure_logger(logger, __name__)
    cfg = get_check_config(scope)
    logger.debug("Reconcile config: %s", cfg)
    diffs = collect_diffs(cfg, logger=logger)
    logger.debug("Diffs collected: %s", diffs)
    diffs = detect_moves(diffs, logger=logger)
    logger.debug("Diffs MOOVE: %s", diffs)
    if apply:
        apply_diffs(diffs, cfg, logger=logger)
