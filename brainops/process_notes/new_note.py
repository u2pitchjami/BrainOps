"""
# process/new_note.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.note import DocumentSemanticType, Note
from brainops.process_notes.new_note_utils import (
    _normalize_abs_posix,
)
from brainops.sql.notes.db_upsert_note import upsert_note_from_model
from brainops.utils.logger import (
    LoggerProtocol,
    ensure_logger,
)
from brainops.utils.normalization import sanitize_yaml_title


def new_note(file_path: str | Path, logger: LoggerProtocol | None = None) -> int:
    """
    Crée/Met à jour une note à partir d'un fichier du vault.

    - Upsert par `file_path` (UNIQUE).
    - Vérifie les doublons si la note vient de IMPORTS_PATH.
    - Tag 'duplicate' + déplacement dans DUPLICATES_PATH si doublon confirmé.
    - Ajoute métadonnées YAML si dans 'Archives'.
    """
    logger = ensure_logger(logger, __name__)
    fp = _normalize_abs_posix(file_path)
    logger.debug(f"[NEW_NOTE] fp : {type(fp)} : {fp}")
    try:
        # ---- construire le modèle Note ---------------------------------------
        title_sani = sanitize_yaml_title(fp.stem)
        modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = Note(
            title=title_sani,
            file_path=fp.as_posix(),
            status="draft",
            summary=None,
            source=None,
            author=None,
            project=None,
            created_at=None,
            modified_at=modified_at,
            word_count=0,
            content_hash=None,
            source_hash=None,
            lang=None,
            doc_type=DocumentSemanticType.UNKNOWN,
            analysis_profile="generic",
        )

        # ---- upsert en DB -----------------------------------------------------
        note_id: int = upsert_note_from_model(note, logger=logger)
        if not note_id:
            raise BrainOpsError(
                "[NOTE] ❌ CREATION NOTE KO",
                code=ErrCode.UNEXPECTED,
                ctx={
                    "step": "new_note",
                    "note_title": note.title,
                    "note_file_path": note.file_path,
                },
            )
        logger.debug(f"[NEW_NOTE] note_id : {note_id}")

    except BrainOpsError as exc:
        exc.with_context({"step": "new_note", "note_title": note.title})
        raise
    except Exception as exc:
        raise BrainOpsError(
            "[NOTE] ❌ CREATION NOTE KO",
            code=ErrCode.UNEXPECTED,
            ctx={
                "step": "new_note",
                "note_title": note.title,
                "root_exc": type(exc).__name__,
                "root_msg": str(exc),
            },
        ) from exc
    return note_id
