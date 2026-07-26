"""
# handlers/process/import_normal.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from brainops.io.utils import count_words
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.folders import FolderType
from brainops.models.metadata import NoteMetadata
from brainops.models.note import DocumentSemanticType
from brainops.models.note_context import NoteContext
from brainops.ollama.ollama_utils import large_or_standard_note
from brainops.process_folders.detect_folder_type import detect_folder_type
from brainops.sql.notes.db_update_notes import update_obsidian_note
from brainops.sql.temp_blocs.db_delete_temp_blocs import delete_blocs_by_path_and_source
from brainops.utils.config import MODEL_EMBEDDINGS
from brainops.utils.files import clean_content
from brainops.utils.logger import get_logger
from brainops.utils.normalization import sanitize_created, sanitize_yaml_title

logger = get_logger("Brainops Imports")

FOLDER_TO_DOCUMENT_TYPE: dict[FolderType, DocumentSemanticType] = {
    FolderType.PERSONAL: DocumentSemanticType.PERSONAL,
    FolderType.PROJECT: DocumentSemanticType.PROJECT,
    FolderType.STORAGE: DocumentSemanticType.ARTICLE,
    FolderType.TUTORIAL: DocumentSemanticType.TUTORIAL,
}


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
            "created_at": sanitize_created(meta_final.created),
            "modified_at": modified_at,
            "word_count": wc,
            "doc_type": meta_final.doc_type,
        }
        update = update_obsidian_note(note_id, updates, logger=logger)
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


def import_normal_note(filepath: str | Path, note_id: int, ctx: NoteContext) -> bool:
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

        folder_type = detect_folder_type(path=src.parent.as_posix())
        meta_yaml.doc_type = FOLDER_TO_DOCUMENT_TYPE.get(
            folder_type,
            DocumentSemanticType.UNKNOWN,
        )

        content = clean_content(ctx.note_content)

        logger.debug("[DEBUG] import_normal : envoi vers make_properties")

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
            logger=logger,
        )
        meta_yaml.status = "note"

        update_normal = update_normal_note(
            final_body_content=content,
            note_id=note_id,
            file_path=Path(filepath),
            meta_final=meta_yaml,
        )
        if not update_normal:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement en base (id=%s)",
                note_id,
            )
            return False

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
