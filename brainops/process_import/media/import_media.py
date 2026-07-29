"""
# handlers/process/import_normal.py
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from brainops.analysis.builder import build_analysis_config
from brainops.embeddings.emb_prompts import build_prompts_main
from brainops.embeddings.emb_utils import select_top_blocks_by_mode
from brainops.embeddings.headers import make_properties
from brainops.header.get_tags_and_summary import _parse_jsonish_tags
from brainops.header.header_utils import hash_source
from brainops.io.paths import exists, remove_file
from brainops.io.utils import count_words
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.models.note_context import NoteContext
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.process_folders.folders import ensure_folder_exists
from brainops.process_import.join.join_header_body import join_header_body
from brainops.process_import.media.media_utils import make_retranscription
from brainops.process_import.split.split_utils import count_tokens
from brainops.process_import.utils.archive import build_synthesis_path
from brainops.process_import.utils.divers import rename_file
from brainops.process_import.utils.paths import path_is_inside
from brainops.sql.notes.db_update_notes import update_obsidian_note, update_obsidian_tags
from brainops.utils.config import ANALYSIS_PROFILES_DIR, IMPORTS_PATH, MODEL_FR, SAV_PATH, Z_STORAGE_PATH
from brainops.utils.files import copy_file_with_date
from brainops.utils.logger import get_logger
from brainops.utils.normalization import sanitize_created, sanitize_yaml_title

logger = get_logger("Brainops Imports Médias")


def update_retranscript(
    final_synth_body_content: str,
    note_id: int,
    synthesis_path: Path,
    meta_synth_final: NoteMetadata,
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
    try:
        wc = count_words(final_synth_body_content)

        modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = {
            "file_path": str(synthesis_path),
            "title": sanitize_yaml_title(meta_synth_final.title),
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


def import_media(filepath: str | Path, note_id: int, ctx: NoteContext) -> bool:
    """
    Étapes : 1) Définir la catégorisation (chemin cible) via process_get_note_type() 2) Renommer/déplacer le fichier
    (rename_file) 3) Mettre à jour la DB (file_path) 4) Brancher sur import_normal()

    Retourne le chemin final (str) ou None en cas d’erreur.
    """
    if not ctx or not ctx.media or not ctx.media.id:
        raise BrainOpsError(
            "[IMPORT] ❌ Contexte invalide",
            code=ErrCode.CONTEXT,
            ctx={"step": "import_normal", "note_id": note_id, "filepath": filepath},
        )
    src = Path(filepath)
    name = src.stem
    suffix = src.suffix
    logger.debug("[INFO] ▶️ LANCEMENT IMPORT MEDIA : (id=%s) path=%s", note_id, src.as_posix())

    try:
        logger.debug("[INFO] Vérification de l'état d'Ollama...")
        if not ctx.note_content or not ctx.note_metadata or not ctx.note_wc:
            raise BrainOpsError(
                "[IMPORT] ❌ données ctx innaccessibles",
                code=ErrCode.CONTEXT,
                ctx={"step": "import_normal", "note_id": note_id, "filepath": filepath},
            )
        meta_yaml = ctx.note_metadata
        if meta_yaml.title is None or meta_yaml.title.strip() == "" or meta_yaml.title.strip().lower() == "untitled":
            meta_yaml.title = sanitize_yaml_title(name)

        if meta_yaml.source is None or meta_yaml.source.strip() == "" or meta_yaml.source.strip().lower() == "none":
            ctx.note_db.source_hash = hash_source(sanitize_yaml_title(meta_yaml.title))
            logger.debug(
                "[DEBUG] source vide ou None, \
                hash basé sur le titre:\
                    %s -> \
                        %s",
                meta_yaml.title,
                ctx.note_db.source_hash,
            )
        else:
            ctx.note_db.source_hash = hash_source(meta_yaml.source)
            logger.debug("[DEBUG] hash basé sur la source: %s -> %s", meta_yaml.source, ctx.note_db.source_hash)

        ctx.analysis = build_analysis_config(
            profile_name=ctx.note_db.analysis_profile,
            profiles_dir=Path(ANALYSIS_PROFILES_DIR),
            logger=ctx.logger,
        )

        top_blocks = select_top_blocks_by_mode(
            note_id=None,
            media_id=ctx.media.id,
            source="embeddings",
            status="processed",
            mode_def=ctx.analysis.selection_mode,
            logger=logger,
        )

        struct_media_prompt, glossary_prompt, tags_prompt, summary_prompt = build_prompts_main(
            blocks=top_blocks,
            ctx=ctx,
        )

        struct_media_prompt_token_count = count_tokens(struct_media_prompt)
        glossary_prompt_token_count = count_tokens(glossary_prompt)
        tags_prompt_token_count = count_tokens(tags_prompt)
        summary_prompt_token_count = count_tokens(summary_prompt)

        # 3) synthèse finale
        final_response = call_ollama_with_retry(struct_media_prompt, model_ollama=MODEL_FR, logger=logger)

        # 3) synthèse finale
        glossary_response = call_ollama_with_retry(glossary_prompt, model_ollama=MODEL_FR, logger=logger)

        # 3) synthèse finale
        tags_response = call_ollama_with_retry(tags_prompt, model_ollama=MODEL_FR, logger=logger)

        tags = _parse_jsonish_tags(tags_response)
        uniq_tags: list[str] = []
        if not tags:
            logger.warning("[WARN] Aucun JSON exploitable trouvé dans la réponse pour les tags.")
        else:
            # dédoublonnage et filtrage des vides
            uniq_tags = []
            seen = set()
            for t in tags:
                if t and t not in seen:
                    uniq_tags.append(t)
                    seen.add(t)

        # 3) synthèse finale
        summary_response = call_ollama_with_retry(summary_prompt, model_ollama=MODEL_FR, logger=logger)

        final_response_token_count = count_tokens(final_response)
        glossary_response_token_count = count_tokens(glossary_response)
        tags_response_token_count = count_tokens(tags_response)
        summary_response_token_count = count_tokens(summary_response)

        media_token_count = struct_media_prompt_token_count + final_response_token_count
        glossary_token_count = glossary_prompt_token_count + glossary_response_token_count
        tags_token_count = tags_prompt_token_count + tags_response_token_count
        summary_token_count = summary_prompt_token_count + summary_response_token_count

        logger.debug(
            f"media_token_count={media_token_count} ---\
            prompt={struct_media_prompt_token_count} + response = {final_response_token_count}"
        )
        logger.debug(
            f"glossary_token_count={glossary_token_count} ---\
            prompt={glossary_prompt_token_count} + response = {glossary_response_token_count}"
        )
        logger.debug(
            f"tags_token_count={tags_token_count} ---\
            prompt={tags_prompt_token_count} + response = {tags_response_token_count}"
        )
        logger.debug(
            f"summary_token_count={summary_token_count} ---\
                     prompt={summary_prompt_token_count} + response = {summary_response_token_count}"
        )

        logger.debug("[DEBUG] import_normal : envoi vers make_properties")
        # 5) Traitement de l'entête
        meta_final: NoteMetadata = make_properties(
            meta_yaml=meta_yaml,
            tags=uniq_tags,
            summary=summary_response if summary_response else "",
            status="archive",
            logger=logger,
        )
        if not meta_final:
            logger.error(
                "[ERREUR] 🚨 Problème lors de la mise à jour des métadonnées pour (id=%s)",
                note_id,
            )
        logger.debug(f"meta_final : {meta_final}")
        # 2) rename
        new_name = rename_file(name=name, created=meta_final.created, note_id=note_id, logger=logger)

        # 3) build Archive path
        output_path = build_synthesis_path(original_path=Z_STORAGE_PATH, original_name=new_name, suffix=suffix)

        # 4) verif presence dossiers
        ensure_folder_exists(folder_path=output_path.parent.as_posix(), logger=logger)

        # 4) Sauvegarde (optionnelle) vers SAV_PATH
        if SAV_PATH:
            try:
                copy_file_with_date(filepath, SAV_PATH, logger=logger)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("[ERREUR] Sauvegarde dans SAV_PATH échouée : %s", exc)
        else:
            logger.warning("[WARN] 🚨 SAV_PATH non défini dans utils.config, sauvegarde ignorée.")

        logger.debug("[DEBUG] Assemblage du corps de la synthèse…")
        final_synth_body_content = make_retranscription(
            content=final_response,
            glossary=glossary_response,
            logger=logger,
        )

        join_synthesis = update_retranscript(
            final_synth_body_content=final_synth_body_content,
            note_id=note_id,
            synthesis_path=output_path,
            meta_synth_final=meta_final,
        )
        if not join_synthesis:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement en base (id=%s)",
                note_id,
            )
            return False

        synthesis_def = join_header_body(
            body=final_synth_body_content,
            meta_yaml=meta_final,
            filepath=output_path,
            write_file=True,
            logger=logger,
        )
        if not synthesis_def:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement de l'archive (id=%s)",
                note_id,
            )
            return False

        if exists(src.as_posix()) and path_is_inside(IMPORTS_PATH, os.path.dirname(src)):
            remove_file(src.as_posix())
            logger.debug("[INFO] Suppression note originale confirmée : %s", src.as_posix())

        logger.info("[INFO] 🏁 IMPORT terminé pour (id=%s)", note_id)
        return True
    except BrainOpsError as exc:
        exc.with_context({"step": "import_normal", "note_id": note_id, "filepath": filepath})
        raise
    except Exception as exc:
        raise BrainOpsError(
            "[IMPORT] ❌ Import normal KO",
            code=ErrCode.UNEXPECTED,
            ctx={
                "step": "import_normal",
                "note_id": note_id,
                "filepath": filepath,
                "root_exc": type(exc).__name__,
                "root_msg": str(exc),
            },
        ) from exc
