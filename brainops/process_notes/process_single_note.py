"""
# handlers/process/process_single_note.py
"""

from __future__ import annotations

import os

from brainops.io.move_error_file import handle_errored_file
from brainops.io.paths import to_abs
from brainops.models.event import QueuedNoteContext
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.note_context import NoteContext
from brainops.process_import.normal.import_normal import import_normal
from brainops.process_import.utils.paths import path_is_inside
from brainops.process_notes.update_note import (
    sync_classification_to_metadata,
    update_note_context,
)
from brainops.process_notes.utils import check_if_tags
from brainops.process_regen.regen_hub import regen_hub
from brainops.utils.config import IMPORTS_PATH, UNCATEGORIZED_PATH, Z_STORAGE_PATH
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger

# ========================================================
# HUB PRINCIPAL
# ========================================================


@with_child_logger
def process_single_note(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol | None = None) -> None:
    """
    Traite une note selon son emplacement et l'événement détecté.
    """
    logger = ensure_logger(logger, __name__)

    if not ctx.note_db.id or not ctx.note_db.status:
        return
    if not ctx.file_path.endswith(".md"):
        logger.debug("Ignoré (extension non .md) : %s", ctx.file_path)
        return

    logger.debug(
        "=== process_single_note start | filepath=%s | id=%s | src=%s",
        ctx.file_path,
        ctx.note_db.id,
        ctx.src_path,
    )

    # --- Déplacement ---
    if ctx.src_path is not None:
        return handle_move(ctx, queued_ctx, logger=logger)

    # --- Création / Modification ---
    return handle_create_or_modify(ctx, queued_ctx, logger=logger)


# ========================================================
# HANDLERS DEPLACEMENT
# ========================================================


def handle_move(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    filepath, src_path = ctx.file_path, ctx.src_path
    base_folder, src_folder = os.path.dirname(filepath), os.path.dirname(str(src_path))
    if not ctx.note_db.id:
        logger.warning("[WARN] 🚨 (fp=%s) : Note ID absent", filepath)
        return

    if not os.path.exists(to_abs(filepath)):
        logger.warning("🚨 Fichier destination inexistant : %s", filepath)
        return

    if is_move_from_uncategorized_to_storage(base_folder, src_folder):
        return handle_move_uncategorized_to_storage(ctx, queued_ctx, logger)

    if path_is_inside(IMPORTS_PATH, base_folder):
        return handle_move_to_imports(ctx, queued_ctx, logger)

    if path_is_inside(Z_STORAGE_PATH, base_folder):
        return handle_move_within_storage(ctx, logger)

    logger.info("[MOVED] 🚨 Déplacement inconnu : %s → %s", src_path, filepath)
    tags = check_if_tags(filepath, ctx.note_db.id, ctx, logger=logger)
    if tags:
        logger.info("[METADATA] ✈️ (id=%s) : Tags générés", ctx.note_db.id)
    update_note_context(ctx)
    return


def handle_move_uncategorized_to_storage(
    ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol
) -> None:
    """Cas : UNCATEGORIZED → STORAGE"""
    try:
        logger.info("[MOVED] ✈️ (id=%s) uncategorized → storage : Import forcé", ctx.note_db.id)
        if not ctx or not ctx.note_db.id:
            raise BrainOpsError(
                "[NOTE] ❌ Données context KO",
                code=ErrCode.CONTEXT,
                ctx={"step": "handle_move_uncategorized_to_storage"},
            )
        # ready = guard_gpu_or_requeue(queued_ctx)
        # if not ready:
        # return

        importok = import_normal(ctx.file_path, ctx.note_db.id, ctx=ctx, force_categ=True)
        if not importok:
            logger.warning("[WARNING] ❌ (id=%s) : Echec Import", ctx.note_db.id)
    except BrainOpsError as exc:
        _handle_exception(ctx, exc, logger)


def handle_move_to_imports(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    """Cas : déplacement vers IMPORTS"""
    try:
        if not ctx or not ctx.note_db.id:
            raise BrainOpsError(
                "[IMPORT] ❌ Données context KO",
                code=ErrCode.CONTEXT,
                ctx={"step": "handle_move_to_imports"},
            )
        logger.info("[MOVED] ✈️ (id=%s) → imports : Import", ctx.note_db.id)
        # ready = guard_gpu_or_requeue(queued_ctx)
        # if not ready:
        # return
        importok = import_normal(ctx.file_path, ctx.note_db.id, ctx=ctx, force_categ=False)
        if not importok:
            logger.warning("[WARNING] ❌ (id=%s) : Echec Import", ctx.note_db.id)
    except BrainOpsError as exc:
        _handle_exception(ctx, exc, logger)


def handle_move_within_storage(ctx: NoteContext, logger: LoggerProtocol) -> None:
    """Cas : déplacement interne dans STORAGE"""
    logger.info("[MOVED] ✈️ (id=%s) Déplacement interne storage", ctx.note_db.id)

    if not ctx.note_classification or not ctx.note_db.id:
        logger.warning("[WARN] ✈️ (id=%s) : Catégories non détectées", ctx.note_db.id)
        return

    logger.info(
        "[MOVED] (id=%s) %s/%s → %s/%s",
        ctx.note_db.id,
        ctx.note_db.cat_name,
        ctx.note_db.sub_cat_name,
        ctx.note_classification.category_name,
        ctx.note_classification.subcategory_name,
    )

    sync_categ = sync_classification_to_metadata(ctx.note_db.id, ctx=ctx, logger=logger)
    if sync_categ:
        logger.info("[METADATA] ✈️ (id=%s) : Entête mise à jour", ctx.note_db.id)

    update_note_context(ctx)
    # if ctx.note_db.status == "synthesis":
    #    check_synthesis_and_trigger_archive(ctx.note_db.id, ctx.file_path, ctx, logger=logger)


# ========================================================
# HANDLERS CREATION / MODIFICATION
# ========================================================


def handle_create_or_modify(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    filepath, base_folder = ctx.file_path, os.path.dirname(ctx.file_path)

    if not os.path.exists(to_abs(filepath)):
        logger.warning("🚨 Fichier inexistant : %s", filepath)
        return

    if path_is_inside(IMPORTS_PATH, base_folder):
        return handle_created_in_imports(ctx, queued_ctx, logger)

    if path_is_inside(Z_STORAGE_PATH, base_folder):
        return handle_updated_in_storage(ctx, queued_ctx, logger)

    logger.info("🚨 (id=%s) Aucune règle identifiée", ctx.note_db.id)
    update_note_context(ctx)
    if ctx.note_db.status == "synthesis":
        if not ctx.note_db.id:
            logger.warning("🚨 (id=%s) Note sans ID", ctx.note_db.id)
        # else:
        # check_synthesis_and_trigger_archive(ctx.note_db.id, filepath, ctx, logger=logger)


def handle_created_in_imports(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    """
    Création dans IMPORTS.
    """
    try:
        if not ctx.note_db.id:
            raise BrainOpsError(
                "[NOTE] ❌ Données context KO",
                code=ErrCode.CONTEXT,
                ctx={"step": "handle_move_uncategorized_in_imports"},
            )

        logger.info("[CREATED] ✨ (id=%s) : Import", ctx.note_db.id)
        # ready = guard_gpu_or_requeue(queued_ctx)
        # if not ready:
        # return
        importok = import_normal(ctx.file_path, ctx.note_db.id, ctx)
        if not importok:
            logger.warning("[WARNING] ❌ (id=%s) : Echec Import", ctx.note_db.id)
    except BrainOpsError as exc:
        _handle_exception(ctx, exc, logger)


def handle_updated_in_storage(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    """
    Modification dans STORAGE.
    """
    if not ctx.note_db.id:
        raise BrainOpsError(
            "[NOTE] ❌ Données context KO",
            code=ErrCode.CONTEXT,
            ctx={"step": "handle_move_uncategorized_in_imports"},
        )
    regen = regen_hub(filepath=ctx.file_path, note_id=ctx.note_db.id, ctx=ctx, queued_ctx=queued_ctx)
    if regen:
        logger.info("[UPDATED] ✨ (id=%s) : Régénération", ctx.note_db.id)
        return
    update_note_context(ctx)
    # if ctx.note_db.parent_id and ctx.note_db.status == "synthesis":
    #     note_parent = get_note_by_id(ctx.note_db.parent_id, logger=logger)
    #     if note_parent and note_parent.id:
    #         ctx_parent = NoteContext(note_parent, file_path=note_parent.file_path, src_path=None, logger=logger)
    #     if ctx_parent.note_metadata and ctx.note_metadata:
    #         ctx_parent.note_metadata.title = ctx.note_metadata.title
    #         ctx_parent.note_metadata.source = ctx.note_metadata.source
    #         ctx_parent.note_metadata.project = ctx.note_metadata.project
    #         ctx_parent.note_metadata.author = ctx.note_metadata.author
    #         if ctx.note_db.media_id and ctx_parent.note_db.media_id:
    #             ctx_parent.note_db.media_id = ctx.note_db.media_id
    #             ctx_parent.note_metadata.doc_type = ctx.note_metadata.doc_type
    #             ctx_parent.note_metadata.provider = ctx.note_metadata.provider
    #             ctx_parent.note_metadata.media_source = ctx.note_metadata.media_source
    #     if ctx_parent.note_classification and ctx.note_classification:
    #         ctx_parent.note_classification.category_id = ctx.note_classification.category_id
    #         ctx_parent.note_classification.subcategory_id = ctx.note_classification.subcategory_id
    #     if ctx_parent.note_content and ctx_parent.note_metadata:
    #         write_metadata_to_note(
    #             filepath=ctx_parent.note_db.file_path,
    #             content=ctx_parent.note_content,
    #             metadata=ctx_parent.note_metadata,
    #             logger=logger,
    #         )


# ========================================================
# HELPERS
# ========================================================


def is_move_from_uncategorized_to_storage(base_folder: str, src_folder: str) -> bool:
    return path_is_inside(Z_STORAGE_PATH, base_folder) and path_is_inside(UNCATEGORIZED_PATH, src_folder)


def _handle_exception(ctx: NoteContext, exc: BrainOpsError, logger: LoggerProtocol) -> None:
    """
    Gestion centralisée des exceptions.
    """
    if not ctx.note_db.id:
        raise BrainOpsError(
            "[NOTE] ❌ Données context KO",
            code=ErrCode.CONTEXT,
            ctx={"step": "handle_move_uncategorized_in_imports"},
        )
    exc.with_context({"step": "process_single_note", "filepath": ctx.file_path, "note_id": ctx.note_db.id})
    logger.exception("[%s] %s | ctx=%r", exc.code.name, str(exc), exc.ctx)
    handle_errored_file(ctx.note_db.id, ctx.file_path, exc, logger=logger)
