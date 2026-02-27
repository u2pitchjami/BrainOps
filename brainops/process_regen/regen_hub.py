"""
#regen_hub.py
"""

from __future__ import annotations

from brainops.io.move_error_file import handle_errored_file
from brainops.models.event import QueuedNoteContext
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.note_context import NoteContext
from brainops.process_import.utils.gpu_guard import guard_gpu_or_requeue
from brainops.process_regen.header_utils import go_header
from brainops.process_regen.synthesis_utils import go_synthesis
from brainops.utils.logger import get_logger

logger = get_logger("Brainops Regen")


def regen_hub(filepath: str, note_id: int, ctx: NoteContext, queued_ctx: QueuedNoteContext) -> bool:
    """
    Hub pour regen.
    """
    trigger_header, trigger_synth = should_trigger_process(note_id, ctx)
    logger.debug(
        "[%s]  (id=%s)  : trigger_header=%s, trigger_synth=%s", ctx.file_path, note_id, trigger_header, trigger_synth
    )

    if trigger_header:
        try:
            ready = guard_gpu_or_requeue(queued_ctx)
            if not ready:
                return False
            go_head = go_header(note_id, ctx, logger=logger)
            if go_head:
                logger.info("[REGEN] ✅ (id=%s) : Regen Header Réussi", note_id)
            else:
                raise BrainOpsError(
                    f"[REGEN] ❌ (id={note_id}) : Regen Header échoué",
                    code=ErrCode.METADATA,
                    ctx={"step": "regen_hub", "note_id": note_id, "filepath": filepath},
                )
        except Exception as exc:
            raise BrainOpsError(
                "[REGEN] ❌ Erreur dans la tentative regen header",
                code=ErrCode.UNEXPECTED,
                ctx={"step": "regen_hub", "note_id": note_id, "filepath": filepath},
            ) from exc

    if trigger_synth:
        try:
            ready = guard_gpu_or_requeue(queued_ctx)
            if not ready:
                return False
            go_synth = go_synthesis(note_id, filepath, ctx, logger=logger)
            if go_synth:
                logger.info("[REGEN] ✅ (id=%s) : Regen Synthèse Réussi", note_id)
            else:
                raise BrainOpsError(
                    f"[REGEN] ❌ (id={note_id}) : Regen Synthèse échoué",
                    code=ErrCode.METADATA,
                    ctx={"step": "regen_hub", "note_id": note_id, "filepath": filepath},
                )

        except BrainOpsError as exc:
            exc.with_context({"step": "regen_hub", "note_id": note_id, "filepath": filepath})
            raise
        except Exception as exc:
            raise BrainOpsError(
                "[REGEN] ❌ Regen KO !!",
                code=ErrCode.UNEXPECTED,
                ctx={
                    "step": "regen_hub",
                    "note_id": note_id,
                    "filepath": filepath,
                    "root_exc": type(exc).__name__,
                    "root_msg": str(exc),
                },
            ) from exc
            handle_errored_file(note_id, filepath, exc, logger=logger)
        return True
    logger.info("[%s]  (id=%s)  : Aucun Regen à réaliser", ctx.file_path, note_id)
    return False


def should_trigger_process(
    note_id: int,
    ctx: NoteContext,
    threshold: int = 100,
) -> tuple[bool, bool]:
    """
    Détermine si une note doit être retraitée en fonction de l'écart de word_count.

    Retourne (trigger, status, parent_id).
    """
    trigger_header = False
    trigger_synth = False
    actual_wc = ctx.note_db.word_count
    new_word_count: int = ctx.note_wc
    try:
        if not ctx.note_db.status or not ctx.note_db.parent_id or not ctx.note_metadata:
            raise BrainOpsError(
                "Données de context KO",
                code=ErrCode.CONTEXT,
                ctx={"note_id": note_id, "step": "should_trigger_process"},
            )
        db_status = str(ctx.note_db.status)
        metadata_status = ctx.note_metadata.status

        word_diff = abs((actual_wc or 0) - new_word_count)
        trigger_wc = word_diff > threshold
        if metadata_status == "archive" and trigger_wc:
            trigger_header = True
            trigger_synth = True
        if metadata_status == "regen_header":
            trigger_header = True
        if db_status == "synthesis" and (trigger_wc or metadata_status == "regen"):
            trigger_synth = True

        return trigger_header, trigger_synth
    except Exception as exc:
        raise BrainOpsError(
            "[TAGS] ❌ Erreur dans la recherche de tags",
            code=ErrCode.METADATA,
            ctx={
                "step": "check_if_tags",
                "note_id": note_id,
                "db_status": db_status,
                "metadata_status": metadata_status,
            },
        ) from exc
