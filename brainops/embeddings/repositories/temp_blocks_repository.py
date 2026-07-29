"""
Implémentation du repository d'embeddings avec la table temp_blocs.
"""

from __future__ import annotations

from collections.abc import Sequence
import json

from brainops.models.media import TempBlockRef
from brainops.sql.temp_blocs.db_error_temp_blocs import mark_bloc_as_error
from brainops.sql.temp_blocs.db_temp_blocs import (
    delete_blocks_from_index,
    get_blocks,
    get_existing_bloc,
    insert_bloc,
    update_bloc_response,
)
from brainops.utils.logger import LoggerProtocol

from ..protocols import (
    EmbeddingBlockProtocol,
    EmbeddingVector,
)


class TempBlocksEmbeddingRepository:
    """
    Persistance des embeddings dans la table temp_blocs.
    """

    def get_existing_vector(
        self,
        *,
        note_id: int | None,
        media_id: int | None,
        block_index: int,
        model: str,
        content_hash: str,
        logger: LoggerProtocol,
    ) -> EmbeddingVector | None:
        """
        Retourne un vecteur existant lorsqu'il est exploitable.
        """

        existing = get_existing_bloc(
            note_id=note_id,
            media_id=media_id,
            block_index=block_index,
            prompt="embedding",
            model=model,
            split_method="embedding_blocks",
            word_limit=0,
            source="embeddings",
            content_hash=content_hash,
            logger=logger,
        )

        if existing is None:
            return None

        logger.debug(
            "Bloc d'embedding existant trouvé : block_id=%d, block_index=%d, content_hash=%s",
            existing.block_id,
            block_index,
            content_hash,
        )

        if existing.status != "processed":
            return None

        if not isinstance(existing.response, str):
            logger.warning(
                "Réponse d'embedding absente ou invalide : block_id=%d",
                existing.block_id,
            )
            return None

        try:
            parsed: object = json.loads(existing.response)
        except json.JSONDecodeError:
            logger.warning(
                "Embedding JSON invalide en base : block_id=%d",
                existing.block_id,
            )
            return None

        if not isinstance(parsed, list):
            logger.warning(
                "Embedding stocké sous un format inattendu : block_id=%d",
                existing.block_id,
            )
            return None

        try:
            return [float(value) for value in parsed]
        except (TypeError, ValueError):
            logger.warning(
                "Embedding contenant des valeurs non numériques : block_id=%d",
                existing.block_id,
            )
            return None

    def register_pending_block(
        self,
        *,
        note_id: int | None,
        media_id: int | None,
        block: EmbeddingBlockProtocol,
        model: str,
        logger: LoggerProtocol,
    ) -> TempBlockRef:
        """
        Retourne ou crée la ligne temporaire associée au bloc.
        """

        existing = get_existing_bloc(
            note_id=note_id,
            media_id=media_id,
            block_index=block.block_index,
            prompt="embedding",
            model=model,
            split_method="embedding_blocks",
            word_limit=0,
            source="embeddings",
            content_hash=block.content_hash,
            logger=logger,
        )

        if existing is not None:
            return TempBlockRef(
                block_id=existing.block_id,
            )

        block_id = insert_bloc(
            note_id=note_id,
            media_id=media_id,
            block_index=block.block_index,
            content=block.text,
            prompt="embedding",
            model=model,
            split_method="embedding_blocks",
            word_limit=0,
            source="embeddings",
            content_hash=block.content_hash,
            logger=logger,
        )

        return TempBlockRef(
            block_id=block_id,
        )

    def save_vector(
        self,
        *,
        block_id: int,
        vector: Sequence[float],
        logger: LoggerProtocol,
    ) -> None:
        """
        Enregistre un vecteur et marque le bloc comme traité.
        """

        try:
            serialized_vector = json.dumps(
                list(vector),
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Impossible de sérialiser le vecteur du bloc {block_id}") from exc

        update_bloc_response(
            block_id=block_id,
            response=serialized_vector,
            status="processed",
            logger=logger,
        )

    def mark_as_error(
        self,
        *,
        block_id: int,
        error_message: str,
        logger: LoggerProtocol,
    ) -> None:
        """
        Marque le bloc temporaire comme étant en erreur.
        """

        logger.error(
            "Embedding en erreur : block_id=%d, erreur=%s",
            block_id,
            error_message,
        )

        mark_bloc_as_error(
            block_id=block_id,
            logger=logger,
        )

    def get_emb_block(
        self,
        note_id: int | None,
        media_id: int | None,
        source: str = "embeddings",
        status: str = "processed",
        logger: LoggerProtocol | None = None,
    ) -> tuple[list[str], list[list[float]]]:
        """
        Récupère l'ensemble des blocks.
        """

        blocks, embeddings = get_blocks(note_id=note_id, media_id=media_id, source=source, status=status, logger=logger)
        return blocks, embeddings

    def del_temp_block(
        self,
        first_index: int,
        note_id: int | None = None,
        media_id: int | None = None,
        source: str = "embeddings",
        status: str = "processed",
        logger: LoggerProtocol | None = None,
    ) -> None:
        """
        Récupère l'ensemble des blocks.
        """

        delete_blocks_from_index(
            note_id=note_id, media_id=media_id, source=source, status=status, first_index=first_index, logger=logger
        )
        return
