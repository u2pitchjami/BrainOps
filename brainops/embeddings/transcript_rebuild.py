"""
Construction et export d'une transcription normalisée depuis Whisper.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from brainops.embeddings.emb_main import (
    EmbeddingProcessingResult,
    TranscriptEmbeddingBlock,
    _validate_indexing_parameters,
    compute_text_hash,
    normalize_embedding_text,
    process_embedding_blocks,
)
from brainops.embeddings.protocols import EmbeddingProviderProtocol, EmbeddingRepositoryProtocol
from brainops.ingest.transcript import (
    ParagraphBuilderConfig,
    TranscriptParagraph,
    build_transcript_paragraphs,
    load_whisper_json,
    parse_whisper_segments,
    rebuild_transcript_sentences,
)
from brainops.utils.config import MODEL_EMBEDDINGS
from brainops.utils.logger import LoggerProtocol, ensure_logger


def resolve_media_json_path(
    storage_path: str,
    *,
    media_root: Path,
) -> Path:
    """
    Construit le chemin absolu du JSON normalisé d'un média.
    """
    source_path = Path(storage_path)

    if source_path.is_absolute():
        media_path = source_path
    else:
        media_path = media_root / source_path

    json_path = media_path.parent / "normalized_transcription.json"

    if not json_path.is_file():
        raise FileNotFoundError(f"JSON de transcription introuvable : {json_path}")

    return json_path


def process_rebuild_embeddings(
    *,
    media_id: int,
    whisper_json_path: Path,
    model_name: str = MODEL_EMBEDDINGS,
    provider: EmbeddingProviderProtocol,
    repository: EmbeddingRepositoryProtocol,
    resume_if_possible: bool = True,
    logger: LoggerProtocol | None = None,
) -> EmbeddingProcessingResult:
    """
    Génère et persiste les embeddings d'une transcription.

    Chaque paragraphe normalisé devient exactement un bloc d'embedding.
    Aucun découpage supplémentaire n'est appliqué.

    Le traitement est isolé bloc par bloc : l'échec d'un paragraphe
    n'interrompt pas les paragraphes suivants.

    Args:
        media_id: Identifiant du média BrainOps.
        whisper_json_path: Chemin vers le fichier JSON de la transcription Whisper.
        model_name: Nom du modèle d'embedding.
        provider: Fournisseur chargé de générer les vecteurs.
        repository: Repository chargé de la persistance.
        resume_if_possible: Réutilise les embeddings compatibles existants.
        logger: Logger BrainOps facultatif.

    Returns:
        Le bilan complet de l'indexation.

    Raises:
        ValueError: Si les paramètres ou la transcription sont invalides.
        BrainOpsError: Si tous les blocs échouent.
    """
    logger = ensure_logger(logger, __name__)
    _validate_indexing_parameters(
        media_id=media_id,
        model_name=model_name,
    )

    paragraphs = load_transcript_paragraphs(
        whisper_json_path=whisper_json_path,
    )

    blocks = build_embedding_blocks_from_paragraphs(paragraphs)

    logger.info(
        ("Début de l'indexation de la transcription : media_id=%d, blocs=%d, modèle=%s"),
        media_id,
        len(blocks),
        model_name,
    )

    if not blocks:
        logger.warning(
            "Aucun paragraphe exploitable dans la transcription : media_id=%d",
            media_id,
        )

    return process_embedding_blocks(
        blocks=blocks,
        note_id=None,
        media_id=media_id,
        model_name=model_name,
        repository=repository,
        provider=provider,
        resume_if_possible=resume_if_possible,
    )


def build_embedding_blocks_from_paragraphs(
    paragraphs: Sequence[TranscriptParagraph],
) -> list[TranscriptEmbeddingBlock]:
    """
    Transforme des paragraphes normalisés en blocs d'embedding.
    """
    blocks: list[TranscriptEmbeddingBlock] = []
    known_indexes: set[int] = set()

    for paragraph in paragraphs:
        normalized_text = normalize_embedding_text(paragraph.text)

        if not normalized_text:
            continue

        if paragraph.index in known_indexes:
            raise ValueError(f"Index de paragraphe dupliqué dans la transcription : {paragraph.index}.")

        known_indexes.add(paragraph.index)

        blocks.append(
            TranscriptEmbeddingBlock(
                block_index=int(paragraph.index),
                text=normalized_text,
                start_seconds=float(paragraph.start),
                end_seconds=float(paragraph.end),
                sentence_indexes=tuple(int(sentence_index) for sentence_index in paragraph.sentence_indexes),
                content_hash=compute_text_hash(normalized_text),
            )
        )

    return blocks


def load_transcript_paragraphs(
    whisper_json_path: Path,
    *,
    config: ParagraphBuilderConfig | None = None,
) -> tuple[TranscriptParagraph, ...]:
    """
    Reconstruit uniquement les paragraphes nécessaires aux embeddings.
    """
    config = config or ParagraphBuilderConfig()
    whisper_data = load_whisper_json(whisper_json_path)

    segments = parse_whisper_segments(
        whisper_data.get("segments", []),
    )

    sentences = rebuild_transcript_sentences(
        segments,
    )

    paragraphs = build_transcript_paragraphs(
        sentences,
        config=config,
    )

    return tuple(paragraphs)


# def load_transcript_for_media(
#     *,
#     media: Media,
#     manifest_path: Path,
#     whisper_json_path: Path,
#     audio_path: Path,
#     config: ParagraphBuilderConfig | None = None,
# ) -> Transcript:
#     """
#     Reconstruit un Transcript depuis un média existant et ses artefacts.
#     """
#     if media.id is None:
#         raise ValueError("Le média doit posséder un identifiant")

#     manifest = load_manifest(manifest_path)
#     whisper_data = load_whisper_json(whisper_json_path)

#     metadata = build_transcript_metadata(
#         media=media,
#         manifest=manifest,
#         whisper_data=whisper_data,
#         audio_path=audio_path,
#     )

#     return build_transcript(
#         whisper_data,
#         metadata=metadata,
#         config=config,
#         source_json_path=whisper_json_path,
#     )


# def build_transcript_metadata(
#     *,
#     media: Media,
#     manifest: AudioManifest,
#     whisper_data: WhisperJSON,
#     audio_path: Path,
# ) -> TranscriptMetadata:
#     """
#     Construit les métadonnées documentaires d'une transcription.

#     La BDD Media est prioritaire. Le manifest et Whisper servent de repli
#     lorsque certaines valeurs ne sont pas persistées.
#     """
#     source = manifest["source"]

#     language = media.language or manifest.get("language") or whisper_data.get("language") or "unknown"

#     return TranscriptMetadata(
#         title=manifest["title"],
#         language=language,
#         audio_filename=audio_path.name,
#         source_type=media.doc_type or source["type"],
#         source_provider=media.provider or source["provider"],
#         source_url=media.source_url or source["url"],
#         show=source.get("show") or None,
#         authors=tuple(manifest.get("authors", [])),
#         published_at=media.published_at or manifest.get("published_at"),
#         analysis_profile=(media.analysis_profile or manifest.get("analysis_profile") or "generic"),
#     )


# def synchronize_existing_media_embeddings(
#     *,
#     media: Media,
#     manifest_path: Path,
#     whisper_json_path: Path,
#     logger: LoggerProtocol | None = None,
# ) -> EmbeddingProcessingResult:
#     """
#     Reconstruit un média existant puis synchronise ses embeddings.
#     """
#     logger = ensure_logger(logger, __name__)

#     try:
#         transcript = load_transcript_for_media(
#             media=media,
#             manifest_path=manifest_path,
#             whisper_json_path=whisper_json_path,
#         )

#         logger.info(
#             ("Transcript reconstruit media_id=%d | segments=%d | sentences=%d | paragraphs=%d"),
#             media.id,
#             len(transcript.segments),
#             len(transcript.sentences),
#             len(transcript.paragraphs),
#         )

#         return process_transcript_embeddings(
#             media_id=media.id,
#             transcript=transcript,
#             model_name=MODEL_EMBEDDINGS,
#             provider=OllamaEmbeddingProvider(),
#             repository=TempBlocksEmbeddingRepository(),
#             resume_if_possible=True,
#         )
#     except (FileNotFoundError, OSError, ValueError) as exc:
#         logger.exception(
#             "Impossible de synchroniser les embeddings media_id=%d",
#             media.id,
#         )
#         raise BrainOpsError(
#             "Reconstruction ou embedding du média impossible",
#             code=ErrCode.MEDIA,
#             ctx={
#                 "media_id": media.id,
#                 "manifest_path": str(manifest_path),
#                 "whisper_json_path": str(whisper_json_path),
#             },
#         ) from exc
