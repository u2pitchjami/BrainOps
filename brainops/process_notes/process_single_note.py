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
from brainops.process_import.media.import_media import import_media
from brainops.process_import.normal.import_normal import import_normal
from brainops.process_import.normal.import_normal_note import import_normal_note
from brainops.process_import.utils.paths import path_is_inside
from brainops.process_notes.update_note import (
    update_note_context,
)
from brainops.utils.config import DUPLICATES_PATH, ERRORED_PATH, IMPORTS_PATH, UNCATEGORIZED_PATH, Z_STORAGE_PATH
from brainops.utils.logger import LoggerProtocol, ensure_logger

# ========================================================
# HUB PRINCIPAL
# ========================================================


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
    # tags = check_if_tags(filepath, ctx.note_db.id, ctx, logger=logger)
    # if tags:
    #     logger.info("[METADATA] ✈️ (id=%s) : Tags générés", ctx.note_db.id)
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

        importok = import_normal(ctx.file_path, ctx.note_db.id, ctx=ctx)
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

        if ctx.media and ctx.media.id:
            logger.info("[MOVED] ✈️ (id=%s) → imports : Media détecté, pas d'import", ctx.note_db.id)
            importok = import_media(ctx.file_path, ctx.note_db.id, ctx=ctx)
        else:
            logger.info("[MOVED] ✈️ (id=%s) → imports : Pas de media, import normal", ctx.note_db.id)
            importok = import_normal(ctx.file_path, ctx.note_db.id, ctx=ctx)

        if not importok:
            logger.warning("[WARNING] ❌ (id=%s) : Echec Import", ctx.note_db.id)
    except BrainOpsError as exc:
        _handle_exception(ctx, exc, logger)


def handle_move_within_storage(ctx: NoteContext, logger: LoggerProtocol) -> None:
    """Cas : déplacement interne dans STORAGE"""
    logger.info("[MOVED] ✈️ (id=%s) Déplacement interne storage", ctx.note_db.id)

    if not ctx.note_db.id:
        logger.warning("[WARN] ✈️ (id=%s) : Ctx absent", ctx.note_db.id)
        return

    logger.info(
        "[MOVED] (id=%s) %s/%s → %s/%s",
        ctx.note_db.id,
    )

    update_note_context(ctx)


# ========================================================
# HANDLERS CREATION / MODIFICATION
# ========================================================


def handle_create_or_modify(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    filepath, base_folder = ctx.file_path, os.path.dirname(ctx.file_path)

    if not os.path.exists(to_abs(filepath)):
        logger.warning("🚨 Fichier inexistant : %s", filepath)
        return

    if (
        path_is_inside(ERRORED_PATH, base_folder)
        or path_is_inside(DUPLICATES_PATH, base_folder)
        or path_is_inside(UNCATEGORIZED_PATH, base_folder)
    ):
        update_note_context(ctx)
        if ctx.note_db.status == "synthesis":
            if not ctx.note_db.id:
                logger.warning("🚨 (id=%s) Note sans ID", ctx.note_db.id)
        return

    if path_is_inside(IMPORTS_PATH, base_folder):
        return handle_created_in_imports(ctx, queued_ctx, logger)

    if path_is_inside(Z_STORAGE_PATH, base_folder):
        return handle_updated_in_storage(ctx, queued_ctx, logger)

    logger.info("🚨 (id=%s) Aucune règle identifiée", ctx.note_db.id)
    return handle_note(ctx, queued_ctx, logger)
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

        if ctx.media and ctx.media.id:
            logger.info("[MOVED] ✈️ (id=%s) → imports : Media détecté, import media", ctx.note_db.id)
            importok = import_media(ctx.file_path, ctx.note_db.id, ctx=ctx)
        else:
            logger.info("[MOVED] ✈️ (id=%s) → imports : Pas de media, import normal", ctx.note_db.id)
            importok = import_normal(ctx.file_path, ctx.note_db.id, ctx=ctx)

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
    trigger = should_trigger_wc(ctx, threshold=100)
    if trigger:
        logger.info("[TRIGGER] ✨ (id=%s) : Trigger process", ctx.note_db.id)
        importok = import_normal(ctx.file_path, ctx.note_db.id, ctx)
        if not importok:
            logger.warning("[WARNING] ❌ (id=%s) : Echec Import", ctx.note_db.id)
    else:
        logger.info("[INFO] ✨ (id=%s) : Pas de trigger process", ctx.note_db.id)

    # regen = regen_hub(filepath=ctx.file_path, note_id=ctx.note_db.id, ctx=ctx, queued_ctx=queued_ctx)
    # if regen:
    #     logger.info("[UPDATED] ✨ (id=%s) : Régénération", ctx.note_db.id)
    #     return
    update_note_context(ctx)


def handle_note(ctx: NoteContext, queued_ctx: QueuedNoteContext, logger: LoggerProtocol) -> None:
    """
    Modification dans projects, tutos, etc...
    """
    if not ctx.note_db.id:
        raise BrainOpsError(
            "[NOTE] ❌ Données context KO",
            code=ErrCode.CONTEXT,
            ctx={"step": "handle_move_uncategorized_in_imports"},
        )
    trigger = should_trigger_wc(ctx, threshold=100)
    if trigger or ctx.note_db.status != "note":
        logger.info("[TRIGGER] ✨ (id=%s) : Trigger process", ctx.note_db.id)
        importok = import_normal_note(ctx.file_path, ctx.note_db.id, ctx)
        if not importok:
            logger.warning("[WARNING] ❌ (id=%s) : Echec Import", ctx.note_db.id)
    else:
        logger.info("[INFO] ✨ (id=%s) : Pas de trigger process", ctx.note_db.id)

    update_note_context(ctx)


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


def should_trigger_wc(
    ctx: NoteContext,
    threshold: int = 100,
) -> bool:
    """
    Détermine si une note doit être retraitée en fonction de l'écart de word_count.

    Retourne (trigger, status, parent_id).
    """
    trigger = False
    actual_wc = ctx.note_db.word_count
    new_word_count: int = ctx.note_wc

    try:
        word_diff = abs((actual_wc or 0) - new_word_count)
        trigger_wc = word_diff > threshold

        if trigger_wc:
            trigger = True

    except Exception as exc:
        raise BrainOpsError(
            "[should_trigger_wc] ❌ Erreur dans la recherche de trigger",
            code=ErrCode.METADATA,
            ctx={
                "step": "should_trigger_wc",
                "note_id": ctx.note_db.id,
            },
        ) from exc

    return trigger
