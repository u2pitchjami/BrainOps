"""
# handlers/process/synthesis.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from langdetect import detect

from brainops.header.header_utils import hash_source
from brainops.io.utils import count_words
from brainops.models.classification import ClassificationResult
from brainops.models.metadata import NoteMetadata
from brainops.models.note import Note
from brainops.process_import.utils.divers import hash_content
from brainops.sql.notes.db_update_notes import update_obsidian_note, update_obsidian_tags
from brainops.sql.notes.db_upsert_note import upsert_note_from_model
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger
from brainops.utils.normalization import sanitize_created, sanitize_yaml_title


@with_child_logger
def update_synthesis(
    final_synth_body_content: str,
    note_id: int,
    synthesis_path: Path,
    meta_synth_final: NoteMetadata,
    classification: ClassificationResult,
    *,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    new_synthesis _summary_

    _extended_summary_

    Args:
        final_synth_body_content (str): _description_
        note_id (int): _description_
        synthesis_path (Path): _description_
        meta_synth_final (NoteMetadata): _description_
        classification (ClassificationResult): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        bool: _description_
    """
    logger = ensure_logger(logger, __name__)
    try:
        wc = count_words(final_synth_body_content)

        modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = {
            "file_path": str(synthesis_path),
            "title": sanitize_yaml_title(meta_synth_final.title),
            "folder_id": classification.folder_id,
            "category_id": classification.category_id,
            "subcategory_id": classification.subcategory_id,
            "status": meta_synth_final.status,
            "summary": meta_synth_final.summary,
            "source": meta_synth_final.source,
            "author": meta_synth_final.author,
            "project": meta_synth_final.project,
            "created_at": sanitize_created(meta_synth_final.created),
            "modified_at": modified_at,
            "word_count": wc,
        }
        update = update_obsidian_note(note_id, updates, logger=logger)
        update_obsidian_tags(note_id, tags=meta_synth_final.tags, logger=logger)
        if not update:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'insertion en db de la synthèse (%s)",
                str(synthesis_path),
            )
            return False
        return True

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Impossible de traiter %s : %s", note_id, exc)
        return False


@with_child_logger
def new_synthesis(
    final_synth_body_content: str,
    note_id: int,
    synthesis_path: Path,
    meta_synth_final: NoteMetadata,
    classification: ClassificationResult,
    *,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    new_synthesis _summary_

    _extended_summary_

    Args:
        final_synth_body_content (str): _description_
        note_id (int): _description_
        synthesis_path (Path): _description_
        meta_synth_final (NoteMetadata): _description_
        classification (ClassificationResult): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        bool: _description_
    """
    logger = ensure_logger(logger, __name__)
    try:
        wc = count_words(final_synth_body_content)
        lang = detect(final_synth_body_content)
        fhash = hash_content(content=final_synth_body_content)
        logger.debug("[DEBUG] new_synthesis: word_count=%d, source=%s", wc, meta_synth_final.source)
        if (
            meta_synth_final.source is None
            or meta_synth_final.source.strip() == ""
            or meta_synth_final.source.strip().lower() == "none"
        ):
            hs = hash_source(sanitize_yaml_title(meta_synth_final.title))
            logger.debug("[DEBUG] source vide ou None, hash basé sur le titre: %s -> %s", meta_synth_final.title, hs)
        else:
            hs = hash_source(meta_synth_final.source)
            logger.debug("[DEBUG] hash basé sur la source: %s -> %s", meta_synth_final.source, hs)
        modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        note = Note(
            title=sanitize_yaml_title(meta_synth_final.title),
            file_path=str(synthesis_path),
            folder_id=classification.folder_id,
            category_id=classification.category_id,
            subcategory_id=classification.subcategory_id,
            status=meta_synth_final.status,
            summary=meta_synth_final.summary,
            source=meta_synth_final.source,
            author=meta_synth_final.author,
            project=meta_synth_final.project,
            created_at=sanitize_created(meta_synth_final.created),
            modified_at=modified_at,
            word_count=wc,
            content_hash=fhash,
            source_hash=hs,
            lang=lang,
        )

        # ---- upsert en DB -----------------------------------------------------
        synth_note_id: int = upsert_note_from_model(note, logger=logger)
        if not synth_note_id:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'insertion en db de la synthèse (%s)",
                str(synthesis_path),
            )
            return False
        update_obsidian_tags(note_id, tags=meta_synth_final.tags, logger=logger)
        updates = {"parent_id": note_id}
        update_obsidian_note(synth_note_id, updates)
        updates = {"parent_id": synth_note_id}
        update_obsidian_note(note_id, updates)
        return True

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Impossible de traiter %s : %s", note_id, exc)
        return False
