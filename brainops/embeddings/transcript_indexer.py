"""
Indexation des paragraphes normalisés d'une transcription.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import math
from typing import Protocol

from brainops.embeddings.models import (
    EmbeddingProcessingFailure,
    EmbeddingProcessingResult,
    EmbeddingVector,
    NoteEmbeddingBlock,
    TranscriptEmbeddingBlock,
)
from brainops.embeddings.protocols import EmbeddingBlockProtocol, EmbeddingProviderProtocol, EmbeddingRepositoryProtocol
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.media import TempBlockRef
from brainops.models.note_context import NoteContext
from brainops.process_import.split.split_main import SplitMethod, split_note_content
from brainops.utils.logger import (
    LoggerProtocol,
    ensure_logger,
)


class TranscriptParagraphProtocol(Protocol):
    """
    Structure minimale attendue pour un paragraphe.
    """

    @property
    def index(self) -> int:
        """
        Index du paragraphe.
        """

    @property
    def text(self) -> str:
        """
        Texte du paragraphe.
        """

    @property
    def start(self) -> float:
        """
        Timestamp de début en secondes.
        """

    @property
    def end(self) -> float:
        """
        Timestamp de fin en secondes.
        """

    @property
    def sentence_indexes(self) -> Sequence[int]:
        """
        Index des phrases composant le paragraphe.
        """


class TranscriptProtocol(Protocol):
    """
    Structure minimale attendue pour une transcription.
    """

    @property
    def paragraphs(
        self,
    ) -> Sequence[TranscriptParagraphProtocol]:
        """
        Paragraphes normalisés de la transcription.
        """


def normalize_embedding_text(text: str) -> str:
    """
    Normalise légèrement un texte avant vectorisation.

    La normalisation supprime les espaces multiples et les retours à la ligne sans modifier le contenu linguistique.
    """
    return " ".join(text.split())


def compute_text_hash(text: str) -> str:
    """
    Calcule l'empreinte SHA-256 d'un texte.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_embedding_vector(
    vector: Sequence[float],
    *,
    block_index: int,
) -> EmbeddingVector:
    """
    Valide et normalise un vecteur d'embedding.

    Args:
        vector: Valeurs retournées par le fournisseur.
        block_index: Index du bloc concerné.

    Returns:
        Une liste de nombres flottants validés.

    Raises:
        ValueError: Si le vecteur est vide ou contient une valeur non finie.
        TypeError: Si le vecteur contient une valeur non numérique.
    """
    if not vector:
        raise ValueError(f"Embedding vide pour le bloc {block_index}.")

    normalized_vector: EmbeddingVector = []

    for value_index, value in enumerate(vector):
        if isinstance(value, bool) or not isinstance(
            value,
            int | float,
        ):
            raise TypeError(
                f"Valeur non numérique dans l'embedding du bloc {block_index}, position {value_index}: {value!r}"
            )

        float_value = float(value)

        if not math.isfinite(float_value):
            raise ValueError(f"Valeur non finie dans l'embedding du bloc {block_index}, position {value_index}.")

        normalized_vector.append(float_value)

    return normalized_vector


def build_transcript_embedding_blocks(
    transcript: TranscriptProtocol,
) -> list[TranscriptEmbeddingBlock]:
    """
    Transforme les paragraphes d'un transcript en blocs d'embedding.

    Les paragraphes sont utilisés directement. Aucun redécoupage n'est
    effectué.

    Args:
        transcript: Transcription normalisée contenant des paragraphes.

    Returns:
        Les blocs prêts à être envoyés au fournisseur d'embeddings.

    Raises:
        ValueError: Si plusieurs paragraphes ont le même index ou si un
            paragraphe contient des métadonnées incohérentes.
    """
    blocks: list[TranscriptEmbeddingBlock] = []
    known_indexes: set[int] = set()

    for paragraph in transcript.paragraphs:
        normalized_text = normalize_embedding_text(paragraph.text)

        if not normalized_text:
            continue

        if paragraph.index in known_indexes:
            raise ValueError(f"Index de paragraphe dupliqué dans la transcription : {paragraph.index}.")

        known_indexes.add(paragraph.index)

        sentence_indexes = tuple(int(sentence_index) for sentence_index in paragraph.sentence_indexes)

        block = TranscriptEmbeddingBlock(
            block_index=int(paragraph.index),
            text=normalized_text,
            start_seconds=float(paragraph.start),
            end_seconds=float(paragraph.end),
            sentence_indexes=sentence_indexes,
            content_hash=compute_text_hash(normalized_text),
        )

        blocks.append(block)

    return blocks


def _validate_indexing_parameters(
    *,
    media_id: int,
    model_name: str,
) -> None:
    """
    Valide les paramètres principaux d'une indexation.
    """
    if media_id <= 0:
        raise ValueError("'note_id' doit être strictement positif.")

    if not model_name.strip():
        raise ValueError("'model_name' ne peut pas être vide.")


def _try_mark_block_as_error(
    *,
    repository: EmbeddingRepositoryProtocol,
    block_id: int | None,
    note_id: int | None,
    media_id: int | None,
    block: EmbeddingBlockProtocol,
    model_name: str,
    error: Exception,
    logger: LoggerProtocol,
) -> None:
    """
    Tente de marquer un bloc enregistré comme étant en erreur.
    """

    if block_id is None:
        logger.warning(
            "Impossible de marquer le bloc en erreur : "
            "aucun block_id disponible, note_id=%s, media_id=%s, "
            "block_index=%d, modèle=%s",
            note_id,
            media_id,
            block.block_index,
            model_name,
        )
        return

    try:
        repository.mark_as_error(
            block_id=block_id,
            error_message=str(error),
            logger=logger,
        )
    except Exception:
        logger.exception(
            "Échec du marquage du bloc en erreur : block_id=%d",
            block_id,
        )


def process_transcript_embeddings(
    *,
    media_id: int,
    transcript: TranscriptProtocol,
    model_name: str,
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
        transcript: Transcription normalisée.
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
    current_logger = ensure_logger(logger, __name__)

    _validate_indexing_parameters(
        media_id=media_id,
        model_name=model_name,
    )

    blocks = build_transcript_embedding_blocks(transcript)

    current_logger.info(
        ("Début de l'indexation de la transcription : media_id=%d, blocs=%d, modèle=%s"),
        media_id,
        len(blocks),
        model_name,
    )

    if not blocks:
        current_logger.warning(
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
        logger=current_logger,
    )


def process_note_embeddings(
    ctx: NoteContext,
    model_name: str,
    provider: EmbeddingProviderProtocol,
    repository: EmbeddingRepositoryProtocol,
    resume_if_possible: bool = True,
    split_method: SplitMethod | None = "auto",
    max_token: int = 1500,
    max_chars: int = 3800,
    logger: LoggerProtocol | None = None,
) -> EmbeddingProcessingResult:
    logger = ensure_logger(logger, __name__)

    if not ctx or not ctx.note_db.id or not ctx.note_content:
        raise ValueError("Erreur dans le NoteContext")

    if split_method is not None:
        text_blocks = split_note_content(
            content=ctx.note_content,
            split_method=split_method,
            max_tokens=max_token,
            max_chars=max_chars,
            logger=logger,
            note_id=ctx.note_db.id,
        )
    else:
        text_blocks = [ctx.note_content]

    blocks = build_note_embedding_blocks(text_blocks)

    return process_embedding_blocks(
        blocks=blocks,
        note_id=ctx.note_db.id,
        media_id=None,
        model_name=model_name,
        repository=repository,
        provider=provider,
        resume_if_possible=resume_if_possible,
        logger=logger,
    )


def build_note_embedding_blocks(
    text_blocks: Sequence[str],
) -> list[NoteEmbeddingBlock]:
    """
    Construit les blocs d'embedding d'une note.
    """
    blocks: list[NoteEmbeddingBlock] = []

    for block_index, text in enumerate(text_blocks):
        normalized_text = normalize_embedding_text(text)

        if not normalized_text:
            continue

        blocks.append(
            NoteEmbeddingBlock(
                block_index=block_index,
                text=normalized_text,
                content_hash=compute_text_hash(normalized_text),
            )
        )

    return blocks


def process_embedding_blocks(
    *,
    blocks: Sequence[EmbeddingBlockProtocol],
    note_id: int | None,
    media_id: int | None,
    model_name: str,
    repository: EmbeddingRepositoryProtocol,
    provider: EmbeddingProviderProtocol,
    resume_if_possible: bool = True,
    logger: LoggerProtocol | None = None,
) -> EmbeddingProcessingResult:
    """
    Vectorise et persiste une séquence de blocs texte.

    Chaque bloc est traité indépendamment. L'échec d'un bloc n'interrompt
    pas le traitement des blocs suivants.

    Args:
        blocks: Blocs texte prêts à être vectorisés.
        note_id: Identifiant de la note propriétaire, ou None.
        media_id: Identifiant du média propriétaire, ou None.
        model_name: Nom du modèle d'embedding.
        repository: Repository de persistance des blocs temporaires.
        provider: Fournisseur chargé de générer les vecteurs.
        resume_if_possible: Réutilise les embeddings compatibles existants.
        logger: Logger BrainOps facultatif.

    Returns:
        Le bilan complet du traitement.

    Raises:
        ValueError: Si le propriétaire ou les paramètres sont invalides.
        BrainOpsError: Si tous les blocs non vides échouent.
    """
    current_logger = ensure_logger(logger, __name__)

    validate_block_owner(
        note_id=note_id,
        media_id=media_id,
    )

    processed_count = 0
    resumed_count = 0
    failures: list[EmbeddingProcessingFailure] = []

    for position, block in enumerate(blocks, start=1):
        current_logger.debug(
            ("Traitement du bloc %d/%d : note_id=%s, media_id=%s, block_index=%d"),
            position,
            len(blocks),
            note_id,
            media_id,
            block.block_index,
        )

        block_ref: TempBlockRef | None = None

        try:
            existing_vector: EmbeddingVector | None = None

            if resume_if_possible:
                existing_vector = repository.get_existing_vector(
                    note_id=note_id,
                    media_id=media_id,
                    block_index=block.block_index,
                    model=model_name,
                    content_hash=block.content_hash,
                    logger=current_logger,
                )

            if existing_vector is not None:
                try:
                    validate_embedding_vector(
                        existing_vector,
                        block_index=block.block_index,
                    )
                except (TypeError, ValueError) as exc:
                    current_logger.warning(
                        (
                            "Embedding existant invalide, recalcul nécessaire : "
                            "note_id=%s, media_id=%s, block_index=%d, erreur=%s"
                        ),
                        note_id,
                        media_id,
                        block.block_index,
                        exc,
                    )
                else:
                    resumed_count += 1

                    current_logger.debug(
                        ("Embedding existant réutilisé : note_id=%s, media_id=%s, block_index=%d"),
                        note_id,
                        media_id,
                        block.block_index,
                    )
                    continue

            block_ref = repository.register_pending_block(
                note_id=note_id,
                media_id=media_id,
                block=block,
                model=model_name,
                logger=current_logger,
            )

            raw_vector = provider.embed(
                text=block.text,
                model=model_name,
                logger=current_logger,
            )

            vector = validate_embedding_vector(
                raw_vector,
                block_index=block.block_index,
            )

            repository.save_vector(
                block_id=block_ref.block_id,
                vector=vector,
                logger=current_logger,
            )

            processed_count += 1

            current_logger.debug(
                ("Embedding enregistré : note_id=%s, media_id=%s, block_index=%d, dimensions=%d"),
                note_id,
                media_id,
                block.block_index,
                len(vector),
            )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            current_logger.exception(
                ("Échec du traitement d'un bloc d'embedding : note_id=%s, media_id=%s, block_index=%d"),
                note_id,
                media_id,
                block.block_index,
            )

            failures.append(
                EmbeddingProcessingFailure(
                    block_index=block.block_index,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )

            _try_mark_block_as_error(
                repository=repository,
                block_id=(block_ref.block_id if block_ref is not None else None),
                note_id=note_id,
                media_id=media_id,
                block=block,
                model_name=model_name,
                error=exc,
                logger=current_logger,
            )

    result = EmbeddingProcessingResult(
        total_blocks=len(blocks),
        processed_blocks=processed_count,
        resumed_blocks=resumed_count,
        failed_blocks=len(failures),
        failures=tuple(failures),
    )

    current_logger.info(
        ("Traitement des embeddings terminé : note_id=%s, media_id=%s, total=%d, nouveaux=%d, repris=%d, erreurs=%d"),
        note_id,
        media_id,
        result.total_blocks,
        result.processed_blocks,
        result.resumed_blocks,
        result.failed_blocks,
    )

    if result.total_blocks > 0 and result.failed_blocks == result.total_blocks:
        raise BrainOpsError(
            "Tous les blocs d'embedding ont échoué",
            code=ErrCode.OLLAMA,
            ctx={
                "note_id": note_id,
                "media_id": media_id,
                "model": model_name,
                "block_count": result.total_blocks,
            },
        )

    return result


def validate_block_owner(
    *,
    note_id: int | None,
    media_id: int | None,
) -> None:
    """
    Vérifie qu'un bloc possède exactement un propriétaire.
    """
    if (note_id is None) == (media_id is None):
        raise BrainOpsError(
            "Un bloc doit appartenir soit à une note, soit à un média",
            code=ErrCode.VALIDATION,
            ctx={
                "note_id": note_id,
                "media_id": media_id,
            },
        )
