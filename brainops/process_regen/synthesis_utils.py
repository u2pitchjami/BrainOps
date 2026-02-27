"""
# utils/regen_utils.py
"""

from __future__ import annotations

from pathlib import Path

from brainops.models.classification import ClassificationResult
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.models.note_context import NoteContext
from brainops.ollama.check_ollama import check_ollama_health
from brainops.process_import.synthese.import_synthese import process_import_syntheses
from brainops.sql.get_linked.db_get_linked_notes_utils import get_file_path
from brainops.sql.notes.db_notes_utils import get_note_by_id
from brainops.sql.temp_blocs.db_delete_temp_blocs import delete_blocs_by_path_and_source
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def regen_synthese_from_archive(
    note_id: int,
    content: str,
    archive_path: str,
    synthesis_path: str,
    meta_final: NoteMetadata,
    classification: ClassificationResult,
    media_id: int | None = None,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Régénère la synthèse d'une note à partir de son archive liée.

    - Purge les blocs temporaires (embeddings / prompts) pour repartir propre.
    - Relance le pipeline de synthèse sur le fichier cible.
    """
    logger = ensure_logger(logger, __name__)
    try:
        logger.info("[INFO] Vérification de l'état d'Ollama...")
        check = check_ollama_health(logger=logger)
        if not check:
            logger.error("[ERREUR] 🚨 Ollama ne répond pas, import annulé pour (id=%s)", note_id)
            raise BrainOpsError(
                "[REGEN] ❌ Check Ollama KO",
                code=ErrCode.OLLAMA,
                ctx={"step": "regen_synthese_from_archive", "note_id": note_id},
            )

        logger.info("[REGEN] Synthèse → note_id=%s ", note_id)
        # Purge de tous les blocs liés à ce chemin (embeddings, prompts, etc.)
        delete_blocs_by_path_and_source(note_id, source="all", logger=logger)

        # Relance synthèse
        synthesis = process_import_syntheses(
            content=content,
            note_id=note_id,
            media_id=media_id,
            archive_path=Path(archive_path),
            synthesis_path=Path(synthesis_path),
            meta_final=meta_final,
            classification=classification,
            regen=True,
            logger=logger,
        )
        if not synthesis:
            raise BrainOpsError(
                "[REGEN] ❌ make_properties KO Regen synthesis annulé",
                code=ErrCode.METADATA,
                ctx={"step": "regen_synthese_from_archive", "note_id": note_id},
            )
        logger.info("[REGEN] Synthèse régénérée pour note_id=%s", note_id)
        return True
    except BrainOpsError as exc:
        logger.exception("[ERROR] regen_synthese_from_archive(%s) : %s", note_id, exc)
        exc.ctx.setdefault("note_id", note_id)
        raise


@with_child_logger
def go_synthesis(
    note_id: int,
    filepath: str,
    ctx: NoteContext,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Regen synthèse.
    """
    logger = ensure_logger(logger, __name__)
    if (
        not ctx
        or not ctx.note_db.status
        or not ctx.note_db.parent_id
        or not ctx.note_content
        or not ctx.note_metadata
        or not ctx.note_classification
    ):
        raise BrainOpsError(
            "[REGEN] ❌ Données context KO Regen annulé",
            code=ErrCode.CONTEXT,
            ctx={"step": "go_header", "note_id": note_id},
        )

    try:
        if str(ctx.note_db.status) == "synthesis":
            note_db_parent = get_note_by_id(ctx.note_db.parent_id, logger=logger)
            if not note_db_parent:
                raise BrainOpsError(
                    "[REGEN] ❌ Données context KO Regen annulé",
                    code=ErrCode.CONTEXT,
                    ctx={"step": "go_header", "note_id": note_id},
                )
                return False

            ctx_parent = NoteContext(
                note_db=note_db_parent, file_path=note_db_parent.file_path, src_path=None, logger=logger
            )
            if (
                not ctx_parent
                or not ctx_parent.note_db.id
                or not ctx_parent.note_db.status
                or not ctx_parent.note_db.parent_id
                or not ctx_parent.note_metadata
                or not ctx_parent.note_classification
                or not ctx_parent.note_content
            ):
                raise BrainOpsError(
                    "[REGEN] ❌ Données context KO Regen annulé",
                    code=ErrCode.CONTEXT,
                    ctx={"step": "go_header", "note_id": note_id},
                )
                return False

        else:
            synthesis_path = get_file_path(note_id=ctx.note_db.parent_id, logger=logger)

        logger.info("[MODIFIED] ✨ (id=%s) : Lancement Regen Synthesis", ctx_parent.note_db.id or note_id)
        synthesis = regen_synthese_from_archive(
            note_id=note_id if ctx.note_db.status == "synthesis" else ctx.note_db.parent_id,
            media_id=ctx_parent.note_db.media_id or ctx.note_db.media_id,
            content=ctx_parent.note_content or ctx.note_content,
            archive_path=ctx_parent.file_path or filepath,
            synthesis_path=filepath if str(ctx.note_db.status) == "synthesis" else synthesis_path,
            meta_final=ctx_parent.note_metadata or ctx.note_metadata,
            classification=ctx_parent.note_classification or ctx.note_classification,
            logger=logger,
        )
        if not synthesis:
            logger.warning(
                "[MODIFIED] 🚨 (note_id=%s) : Échec de la régénération de la synthèse",
                note_id,
            )
            return False
    except BrainOpsError as exc:
        logger.exception("[%s] %s | ctx=%r", exc.code, str(exc), exc.ctx)
    logger.info("[REGEN] ✅ (id=%s) : Regen Synthèse Réussi", note_id)
    return True
