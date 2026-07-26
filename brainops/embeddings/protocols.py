"""
Contrats des services d'embedding.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from brainops.models.media import TempBlockRef
from brainops.utils.logger import LoggerProtocol

EmbeddingVector = list[float]


class EmbeddingBlockProtocol(Protocol):
    """
    Contrat minimal d'un bloc d'embedding.
    """

    @property
    def block_index(self) -> int:
        """
        Position logique du bloc dans le document.
        """
        ...

    @property
    def text(self) -> str:
        """
        Texte normalisé envoyé au provider.
        """
        ...

    @property
    def content_hash(self) -> str:
        """
        Empreinte du texte normalisé.
        """
        ...


class EmbeddingProviderProtocol(Protocol):
    """
    Contrat d'un fournisseur de vecteurs.
    """

    def embed(
        self,
        *,
        text: str,
        model: str,
        logger: LoggerProtocol,
    ) -> EmbeddingVector:
        """
        Génère un vecteur depuis un texte.
        """


class EmbeddingRepositoryProtocol(Protocol):
    """
    Contrat de persistance des blocs et vecteurs.
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
        Retourne un vecteur déjà calculé.
        """

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
        Enregistre un bloc en attente.
        """

    def save_vector(
        self,
        *,
        block_id: int,
        vector: Sequence[float],
        logger: LoggerProtocol,
    ) -> None:
        """
        Enregistre le vecteur calculé.
        """

    def mark_as_error(
        self,
        *,
        block_id: int,
        error_message: str,
        logger: LoggerProtocol,
    ) -> None:
        """
        Marque un bloc en erreur.
        """
