"""
# utils/divers.py
"""

from __future__ import annotations

from brainops.header.get_tags_and_summary import get_tags_from_ollama
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.note_context import NoteContext
from brainops.sql.notes.db_update_notes import update_obsidian_tags
from brainops.utils.logger import LoggerProtocol, ensure_logger


def check_if_tags(
    filepath: str,
    note_id: int,
    ctx: NoteContext,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Vérifie si des tags doivent être ajoutés et les met à jour si besoin.

    Retourne True si des tags ont été ajoutés, False sinon.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug(
        "[TAGS] Vérification des tags pour note_id=%s, filepath=%s, wc=%s, status=%s",
        note_id,
        filepath,
        ctx.note_wc,
        ctx.note_db.status,
    )
    tags = []
    try:
        if not ctx or not ctx.note_content:
            raise BrainOpsError(
                "[REGEN] ❌ Données context KO Regen annulé",
                code=ErrCode.CONTEXT,
                ctx={"step": "go_header", "note_id": note_id},
            )

        if ctx.note_wc > 100:
            tags = get_tags_from_ollama(content=ctx.note_content, note_id=note_id, logger=logger)

        if tags:
            logger.debug("[DEBUG] Tags à ajouter : %s", tags)
            if update_obsidian_tags(note_id, tags=tags, logger=logger):
                logger.info("[INFO] Tags mis à jour avec succès : %s", tags)
                return True
        return False
    except Exception as exc:
        raise BrainOpsError(
            "[TAGS] ❌ Erreur dans la recherche de tags",
            code=ErrCode.METADATA,
            ctx={
                "step": "check_if_tags",
                "file": filepath,
                "note_id": note_id,
                "status": ctx.note_db.status,
                "word_count": ctx.note_wc,
            },
        ) from exc
