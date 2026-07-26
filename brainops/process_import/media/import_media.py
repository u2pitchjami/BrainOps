"""
# handlers/process/import_normal.py
"""

from __future__ import annotations

from pathlib import Path

from brainops.analysis.builder import build_analysis_config
from brainops.header.header_utils import hash_source
from brainops.header.headers import make_properties
from brainops.io.paths import exists, remove_file
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.metadata import NoteMetadata
from brainops.models.note_context import NoteContext
from brainops.process_folders.folders import ensure_folder_exists
from brainops.process_import.media.import_synthese import (
    process_import_syntheses,
)
from brainops.process_import.utils.archive import build_synthesis_path
from brainops.process_import.utils.divers import rename_file
from brainops.utils.config import ANALYSIS_PROFILES_DIR, SAV_PATH, Z_STORAGE_PATH
from brainops.utils.files import clean_content, copy_file_with_date
from brainops.utils.logger import get_logger
from brainops.utils.normalization import sanitize_yaml_title

logger = get_logger("Brainops Imports")


def import_media(filepath: str | Path, note_id: int, ctx: NoteContext) -> bool:
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
    logger.debug("[DEBUG] +++ ▶️ PRE IMPORT NORMAL pour %s", src.as_posix())

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

        # 5) Génération de la synthèse
        synthesis = process_import_syntheses(
            content=content,
            note_id=note_id,
            synthesis_path=output_path,
            meta_final=meta_final,
            ctx=ctx,
            logger=logger,
        )

        if not synthesis:
            logger.error(
                "[ERREUR] 🚨 Problème lors de la génération de la synthèse pour (id=%s)",
                note_id,
            )
            raise BrainOpsError(
                "[IMPORT] ❌ Echec de la génération de la synthèse",
                code=ErrCode.UNEXPECTED,
                ctx={"step": "import_normal", "note_id": note_id, "filepath": filepath},
            )
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
