"""
# process/update_note.py
"""

from __future__ import annotations

from pathlib import Path

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.note_context import NoteContext
from brainops.process_import.join.join_header_body import join_header_body
from brainops.sql.notes.db_update_medias import _ALLOWED_COLUMNS_MEDIAS, update_obsidian_medias
from brainops.sql.notes.db_update_notes import (
    update_obsidian_note,
)
from brainops.utils.logger import LoggerProtocol, ensure_logger


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


def sync_classification_to_metadata(note_id: int, ctx: NoteContext, *, logger: LoggerProtocol | None = None) -> bool:
    """
    Vérifie si la classification (cat/subcat) du contexte diffère de celle stockée dans Note. Si oui, écrit la mise à
    jour dans le header YAML de la note.

    Retourne True si une mise à jour a été faite, False sinon.
    """
    logger = ensure_logger(logger, __name__)
    if not ctx or not ctx.note_classification or not ctx.note_metadata:
        raise BrainOpsError(
            "[REGEN] ❌ Données context KO Regen annulé",
            code=ErrCode.CONTEXT,
            ctx={"step": "sync_classification_to_metadata", "note_id": note_id},
        )

    db_cat = ctx.note_db.cat_name or ""
    db_subcat = ctx.note_db.sub_cat_name or ""
    new_cat = ctx.note_classification.category_name
    new_subcat = ctx.note_classification.subcategory_name or ""

    if (db_cat != new_cat) or (db_subcat != new_subcat):
        logger.info(
            "[CLASSIFICATION SYNC] Mise à jour YAML (cat: %s→%s, subcat: %s→%s)",
            db_cat,
            new_cat,
            db_subcat,
            new_subcat,
        )

        # On ajuste l'objet metadata avant de l'écrire
        ctx.note_metadata.category = new_cat
        ctx.note_metadata.subcategory = new_subcat

        # Mise à jour du header YAML dans le fichier
        join_header_body(
            body=ctx.note_content or "",
            meta_yaml=ctx.note_metadata,
            filepath=Path(ctx.file_path),
            logger=logger,
        )

        return True

    logger.debug("[CLASSIFICATION SYNC] Pas de différence (cat=%s, subcat=%s)", db_cat, db_subcat)
    return False


# # @with_child_logger
# # def update_note(
# #     ctx: NoteContext,
# #     *,
# #     logger: LoggerProtocol | None = None,
# # ) -> None:
# #     """
# #     Met à jour une note existante dans la base en utilisant NoteContext.
# #     - Compare DB vs fichier (metadata/classification/wc…)
# #     - Met à jour obsidian_notes si nécessaire
# #     - Déclenche regen_tags uniquement si wc modifié ET note hors Z_STORAGE_PATH
# #     - Met à jour le header YAML si categ/subcateg changés
# #     """
# #     logger = ensure_logger(logger, __name__)
# #     dp = Path(ctx.note_db.file_path)

# #     if not wait_for_file(dp, logger=logger):
# #         logger.warning("⚠️ Fichier introuvable, skip : %s", dp)
# #         return

# #     try:
# #         # 1) Calculer différences DB ↔ fichier
# #         diffs = ctx.sync_with_db()

# #         # 2) Update DB si nécessaire
# #         if diffs:
# #             update_obsidian_note(ctx.note_db.id, diffs, logger=logger)
# #             logger.info("[UPDATE_NOTE] Note mise à jour: %s (id=%s)", dp, ctx.note_db.id)

# #         # 3) Tags auto seulement si wc changé ET hors Z_STORAGE_PATH
# #         if "word_count" in diffs and not path_is_inside(Z_STORAGE_PATH, dp):
# #             logger.debug("[UPDATE_NOTE] Post-action: regen_tags (via check_if_tags)")
# #             check_tags = check_if_tags(
# #                 filepath=dp.as_posix(),
# #                 note_id=ctx.note_db.id,
# #                 wc=ctx.note_wc,
# #                 status=ctx.note_classification.status,
# #                 classification=ctx.note_classification,
# #                 logger=logger,
# #             )
# #             if check_tags:
# #                 logger.info("[UPDATE_NOTE] Tags ajoutés automatiquement")

# #         # 4) Mise à jour du header YAML si categ/subcateg changés
# #         if path_is_inside(Z_STORAGE_PATH, dp):
# #             if (
# #                 ctx.note_classification.category_name != ctx.note_metadata.category
# #                 or ctx.note_classification.subcategory_name != (ctx.note_metadata.subcategory or "")
# #             ):
# #                 updates_head = {"category": ctx.note_classification.category_name}
# #                 if ctx.note_classification.subcategory_name:
# #                     updates_head["subcategory"] = ctx.note_classification.subcategory_name

# #                 merge = merge_metadata_in_note(filepath=dp, updates=updates_head, logger=logger)
# #                 logger.debug(f"[UPDATE_NOTE] merge header : {merge}")

# #     except Exception as exc:
# #         raise BrainOpsError("Update Note KO", code=ErrCode.UNEXPECTED, ctx={"note_id": ctx.note_db.id}) from exc


# @with_child_logger
# def update_note_old(
#     note_id: int,
#     dest_path: str | Path,
#     src_path: str | Path | None = None,
#     logger: LoggerProtocol | None = None,
# ) -> None:
#     """
#     Met à jour une note existante dans la base, y compris en cas de déplacement.

#     - lit l’entête YAML (fallback avec valeurs DB si manquantes)
#     - recalcule categ/subcateg depuis le path effectif
#     - met à jour obsidian_notes
#     - synchronise tags si nécessaire
#     - applique des actions selon status (synthesis / regen / regen_header)
#     """
#     logger = ensure_logger(logger, __name__)
#     dp = Path(dest_path)
#     sp = Path(src_path) if src_path is not None else None
#     logger.debug("[UPDATE_NOTE] note_id=%s | dest=%s | src=%s", note_id, dp, sp)

#     if not wait_for_file(dp, logger=logger):
#         logger.warning("⚠️ Fichier introuvable, skip : %s", dp)
#         return

#     regen_synth_trigger = False
#     regen_header_trigger = False
#     regen_tags_trigger = False

#     try:
#         # 1) Métadonnées depuis YAML
#         meta = read_metadata_object(str(dp), logger=logger)
#         logger.debug(f"meta : {meta}")
#         title_yaml = meta.title or dp.stem.replace("_", " ").replace(":", " ")
#         status_yaml = meta.status or "draft"
#         summary_yaml = meta.summary
#         source_yaml = meta.source
#         author_yaml = meta.author
#         project_yaml = meta.project
#         created_yaml = meta.created
#         categ_yaml = meta.category
#         subcateg_yaml = meta.subcategory or None

#         if status_yaml == "regen":
#             regen_synth_trigger = True
#         elif status_yaml == "regen_hearder":
#             regen_header_trigger = True

#         # 2) Contexte catégories depuis le chemin
#         base_folder = str(dp.parent)
#         classification = get_category_context_from_folder(base_folder, logger=logger)

#         logger.debug(
#             "[UPDATE_NOTE] path→categ: %s / %s | ids: %s / %s",
#             classification.category_name,
#             classification.subcategory_name,
#             classification.category_id,
#             classification.subcategory_id,
#         )

#         # 4) Valeurs finales (YAML prioritaire si présent)
#         title = sanitize_yaml_title(title_yaml)
#         created = sanitize_created(created_yaml)
#         author = author_yaml
#         source = source_yaml
#         project = project_yaml
#         status_temp = status_yaml
#         summary = summary_yaml

#         new_status = classification.status
#         def_status = new_status or status_temp

#         actual_db_wc = get_note_wc(note_id, logger=logger) or 0
#         wc = count_words(content=None, filepath=dp, logger=logger)
#         if wc != actual_db_wc:
#             regen_tags_trigger = True

#         # 6) Update DB principal
#         updates = {
#             "file_path": str(dp),
#             "title": title,
#             "folder_id": classification.folder_id,
#             "category_id": classification.category_id,
#             "subcategory_id": classification.subcategory_id,
#             "status": def_status,
#             "summary": summary,
#             "source": source,
#             "author": author,
#             "project": project,
#             "created_at": created,
#             "word_count": wc,
#         }
#         update_obsidian_note(note_id, updates, logger=logger)

#         logger.info("[UPDATE_NOTE] Note mise à jour: %s (id=%s)", dp, note_id)

#         # 9) Actions selon status
#         if def_status == "synthesis":
#             logger.debug("[UPDATE_NOTE] Post-action: check_synthesis_and_trigger_archive")
#             check_synthesis_and_trigger_archive(note_id, str(dp), logger=logger)
#         if regen_synth_trigger:
#             logger.debug("[UPDATE_NOTE] Post-action: regen_synthese_from_archive")
#             regen_synthese_from_archive(note_id, filepath=str(dp))
#         if regen_header_trigger:
#             logger.debug("[UPDATE_NOTE] Post-action: regen_header")
#             regen_header(note_id, str(dp))

#         if regen_tags_trigger:
#             logger.debug("[UPDATE_NOTE] Post-action: regen_tags (via check_if_tags)")
#             check_tags = check_if_tags(
#                 filepath=dp.as_posix(),
#                 note_id=note_id,
#                 wc=wc,
#                 status=def_status,
#                 classification=classification,
#                 logger=logger,
#             )
#             if check_tags:
#                 logger.info("[UPDATE_NOTE] Tags ajoutés automatiquement")

#         if path_is_inside(Z_STORAGE_PATH, dp):
#             if classification.category_name != categ_yaml or (classification.subcategory_name or "") != (
#                 subcateg_yaml or ""
#             ):
#                 if classification.subcategory_name is None:
#                     updates_head: dict[str, str | int | list[str]] = {
#                         "category": classification.category_name,
#                     }
#                 else:
#                     updates_head = {
#                         "category": classification.category_name,
#                         "subcategory": classification.subcategory_name,
#                     }
#                 merge = merge_metadata_in_note(filepath=dp, updates=updates_head, logger=logger)
#                 logger.debug(f"[UPDATE_NOTE] merge header : {merge}")
#         return

#     except Exception as exc:
#         raise BrainOpsError("Update Note KO", code=ErrCode.UNEXPECTED, ctx={"status": "ollama"}) from exc
#         return None
