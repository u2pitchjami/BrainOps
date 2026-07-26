"""
# handlers/process/import_normal.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from brainops.analysis.builder import build_analysis_config
from brainops.header.header_utils import hash_source
from brainops.header.headers import make_properties
from brainops.io.paths import exists, remove_file
from brainops.io.utils import count_words
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.models.note import DocumentSemanticType
from brainops.models.note_context import NoteContext
from brainops.ollama.ollama_utils import large_or_standard_note
from brainops.process_folders.folders import ensure_folder_exists
from brainops.process_import.join.join_header_body import join_header_body
from brainops.process_import.utils.archive import build_synthesis_path
from brainops.process_import.utils.divers import rename_file
from brainops.sql.notes.db_update_notes import update_obsidian_note, update_obsidian_tags
from brainops.sql.temp_blocs.db_delete_temp_blocs import delete_blocs_by_path_and_source
from brainops.utils.config import ANALYSIS_PROFILES_DIR, MODEL_EMBEDDINGS, SAV_PATH, Z_STORAGE_PATH
from brainops.utils.files import clean_content, copy_file_with_date
from brainops.utils.logger import get_logger
from brainops.utils.normalization import sanitize_created, sanitize_yaml_title

logger = get_logger("Brainops Imports")


def update_normal_note(final_body_content: str, note_id: int, file_path: Path, meta_final: NoteMetadata) -> bool:
    """
    Met à jour une note normale dans la base de données.

    _extended_summary_

    Args:
        final_body_content (str): _description_
        note_id (int): _description_
        file_path (Path): _description_
        meta_final (NoteMetadata): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        bool: _description_
    """
    try:
        wc = count_words(final_body_content)

        modified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = {
            "file_path": str(file_path),
            "title": sanitize_yaml_title(meta_final.title),
            "status": meta_final.status,
            "summary": meta_final.summary,
            "source": meta_final.source,
            "author": meta_final.author,
            "project": meta_final.project,
            "created_at": sanitize_created(meta_final.created),
            "modified_at": modified_at,
            "word_count": wc,
            "doc_type": meta_final.doc_type,
        }
        update = update_obsidian_note(note_id, updates, logger=logger)
        update_obsidian_tags(note_id, tags=meta_final.tags, logger=logger)
        if not update:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'insertion en db de la synthèse (%s)",
                str(file_path),
            )
            return False
        return True

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Impossible de traiter %s : %s", note_id, exc)
        return False


def import_normal(filepath: str | Path, note_id: int, ctx: NoteContext) -> bool:
    """
    Étapes : 1) Définir la catégorisation (chemin cible) via process_get_note_type() 2) Renommer/déplacer le fichier
    (rename_file) 3) Mettre à jour la DB (file_path) 4) Brancher sur import_normal()

    Retourne le chemin final (str) ou None en cas d’erreur.
    """
    if not ctx:
        raise BrainOpsError(
            "[IMPORT] ❌ Contexte invalide",
            code=ErrCode.CONTEXT,
            ctx={"step": "import_normal", "note_id": note_id, "filepath": filepath},
        )
    src = Path(filepath)
    name = src.stem
    suffix = src.suffix
    logger.info("[INFO] ▶️ LANCEMENT IMPORT : (id=%s) path=%s", note_id, src.as_posix())

    try:
        logger.info("[INFO] Vérification de l'état d'Ollama...")
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

        if ctx.note_db.doc_type.strip().lower() == "unknown":
            new_doc_type = DocumentSemanticType.ARTICLE
            ctx.note_db.doc_type = new_doc_type
            meta_yaml.doc_type = new_doc_type
            logger.debug("[DEBUG] doc_type vide ou None : %s", ctx.note_db.doc_type)

        ctx.analysis = build_analysis_config(
            profile_name=ctx.note_db.analysis_profile,
            profiles_dir=Path(ANALYSIS_PROFILES_DIR),
            logger=ctx.logger,
        )

        content = clean_content(ctx.note_content)

        logger.debug("[DEBUG] import_normal : envoi vers make_properties")
        # 5) Traitement de l'entête
        meta_final: NoteMetadata = make_properties(
            content=content,
            meta_yaml=meta_yaml,
            note_id=note_id,
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

        # 1) création des embeddings + stockage des blocs (process_large_note côté projet)
        delete_blocs_by_path_and_source(
            note_id=note_id,
            source="embeddings",
            logger=logger,
        )
        _ = large_or_standard_note(
            content=content,
            source="embeddings",
            process_mode="large_note" if count_words(content) > 1500 else "standard_note",
            prompt_name="embeddings",
            model_ollama=MODEL_EMBEDDINGS,
            write_file=False,
            split_method="auto",
            max_chars=3800,
            max_tokens=1500,
            note_id=note_id,
            persist_blocks=True,
            send_to_model=True,
            resume_if_possible=False,
            logger=logger,
        )

        update_normal = update_normal_note(
            final_body_content=content,
            note_id=note_id,
            file_path=output_path,
            meta_final=meta_final,
        )
        if not update_normal:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement en base (id=%s)",
                note_id,
            )
            return False

        note_def = join_header_body(
            body=content,
            meta_yaml=meta_final,
            filepath=output_path,
            write_file=True,
            logger=logger,
        )
        if not note_def:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement de l'archive (id=%s)",
                note_id,
            )
            return False

        if exists(src.as_posix()):
            remove_file(src.as_posix())
            logger.info("[INFO] Suppression note originale confirmée : %s", src.as_posix())

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
