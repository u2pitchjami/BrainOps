# """
# # utils/regen_utils.py
# """

# from __future__ import annotations

# from pathlib import Path

# from brainops.header.headers import make_properties
# from brainops.models.classification import ClassificationResult
# from brainops.models.exceptions import BrainOpsError, ErrCode
# from brainops.models.metadata import NoteMetadata
# from brainops.models.note_context import NoteContext
# from brainops.ollama.check_ollama import check_ollama_health
# from brainops.process_import.join.join_header_body import join_header_body
# from brainops.utils.files import clean_content
# from brainops.utils.logger import LoggerProtocol, ensure_logger


# def go_header(
#     note_id: int,
#     ctx: NoteContext,
#     logger: LoggerProtocol | None = None,
# ) -> bool:
#     """
#     Génère l'en-tête de la note.
#     """
#     logger = ensure_logger(logger, __name__)
#     logger.info("[REGEN] ✨ (id=%s) : Lancement Regen Header", note_id)
#     logger.debug("[DEBUG] +++ ▶️ REGEN HEADER pour %s", note_id)
#     if (
#         not ctx
#         or not ctx.note_db.status
#         or not ctx.note_metadata
#         or not ctx.note_classification
#         or not ctx.note_content
#         or not ctx.brainops_original
#         or not ctx.file_path
#     ):
#         raise BrainOpsError(
#             "[REGEN] ❌ Données context KO Regen annulé",
#             code=ErrCode.CONTEXT,
#             ctx={"step": "go_header", "note_id": note_id},
#         )

#     meta_yaml = ctx.note_metadata
#     classification = ctx.note_classification
#     db_status = str(ctx.note_db.status)
#     content = ctx.note_content
#     original_content = ctx.brainops_original

#     logger.info("[REGEN] ✨ (id=%s) : Lancement Regen Header", note_id)
#     try:
#         header = regen_header(note_id, original_content, meta_yaml, classification, db_status)
#         if not header:
#             logger.warning(
#                 "[REGEN] 🚨 (id=%s) : Échec de la régénération de l'en-tête",
#                 note_id,
#             )
#             return False
#         ctx.note_metadata = header
#         write = join_header_body(body=content, meta_yaml=header, filepath=Path(ctx.file_path), logger=logger)
#         if write:
#             logger.info("[REGEN_HEADER] %s écriture de l'entête réussi", ctx.file_path)
#             return True
#         return False

#     except BrainOpsError as exc:
#         raise BrainOpsError(
#             "[REGEN] ❌ make_properties KO Regen Header annulé",
#             code=ErrCode.METADATA,
#             ctx={"step": "regen_header", "note_id": note_id},
#         ) from exc


# def regen_header(
#     note_id: int,
#     content: str,
#     meta_yaml: NoteMetadata,
#     classification: ClassificationResult,
#     status: str,
#     logger: LoggerProtocol | None = None,
# ) -> NoteMetadata:
#     """
#     Régénère l'entête (tags, summary, champs YAML) d'une note.

#     Détermine le 'status' attendu :
#       - si parent_id est fourni : 'synthesis' si le parent est 'archive', sinon 'archive'
#       - sinon : 'archive' si le chemin contient un segment 'Archives' (insensible casse), sinon 'synthesis'
#     """
#     logger = ensure_logger(logger, __name__)
#     try:
#         logger.info("[INFO] Vérification de l'état d'Ollama...")
#         check = check_ollama_health(logger=logger)
#         if not check:
#             logger.error("[ERREUR] 🚨 Ollama ne répond pas, import annulé pour (id=%s)", note_id)
#             raise BrainOpsError(
#                 "[REGEN] ❌ Check Ollama KO",
#                 code=ErrCode.OLLAMA,
#                 ctx={"step": "regen_header", "note_id": note_id},
#             )
#         content = clean_content(content)

#         logger.info("[REGEN_HEADER] %s → status=%s", note_id, classification.status)
#         properties = make_properties(
#             content=content,
#             meta_yaml=meta_yaml,
#             note_id=note_id,
#             status=str(classification.status),
#             logger=logger,
#         )
#         if not properties:
#             raise BrainOpsError(
#                 "[REGEN] ❌ make_properties KO Regen Header annulé",
#                 code=ErrCode.METADATA,
#                 ctx={"step": "regen_header", "note_id": note_id},
#             )
#         return properties
#     except BrainOpsError as exc:
#         raise BrainOpsError(
#             "[REGEN] ❌ Regen Header KO",
#             code=ErrCode.METADATA,
#             ctx={"step": "regen_header", "note_id": note_id},
#         ) from exc
#         raise
