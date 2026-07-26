"""
# process/update_note.py
"""

from __future__ import annotations

from brainops.models.note_context import NoteContext
from brainops.sql.notes.db_update_medias import _ALLOWED_COLUMNS_MEDIAS, update_obsidian_medias
from brainops.sql.notes.db_update_notes import (
    update_obsidian_note,
)


def update_note_context(ctx: NoteContext) -> None:
    """
    Complète les infos manquantes après un insert minimal.
    """
    diffs = ctx.sync_with_db()
    if diffs and ctx.note_db.id:
        ctx.print_diff()
        update_obsidian_note(ctx.note_db.id, diffs)
        if ctx.note_db.media_id:
            update_obsidian_medias(ctx.note_db.media_id, diffs)
        # mise à jour locale de Note
        for k, v in diffs.items():
            if k in _ALLOWED_COLUMNS_MEDIAS:
                setattr(ctx.media, k, v)
            else:
                setattr(ctx.note_db, k, v)
