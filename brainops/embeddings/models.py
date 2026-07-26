"""
Modèles métier utilisés pour l'indexation des embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass

type EmbeddingVector = list[float]


@dataclass(frozen=True, slots=True)
class NoteEmbeddingBlock:
    block_index: int
    text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class TranscriptEmbeddingBlock:
    """
    Paragraphe de transcription prêt à être vectorisé.

    Attributes:
        block_index: Index stable du paragraphe dans la transcription.
        text: Texte normalisé envoyé au modèle d'embedding.
        start_seconds: Début du paragraphe dans le média source.
        end_seconds: Fin du paragraphe dans le média source.
        sentence_indexes: Index des phrases composant le paragraphe.
        content_hash: Empreinte SHA-256 du texte normalisé.
    """

    block_index: int
    text: str
    start_seconds: float
    end_seconds: float
    sentence_indexes: tuple[int, ...]
    content_hash: str

    def __post_init__(self) -> None:
        """
        Vérifie la cohérence du bloc.
        """
        if self.block_index < 0:
            raise ValueError("'block_index' ne peut pas être négatif.")

        if not self.text.strip():
            raise ValueError("Le texte d'un bloc d'embedding ne peut pas être vide.")

        if self.start_seconds < 0:
            raise ValueError("'start_seconds' ne peut pas être négatif.")

        if self.end_seconds < self.start_seconds:
            raise ValueError("'end_seconds' doit être supérieur ou égal à 'start_seconds'.")

        if len(self.content_hash) != 64:
            raise ValueError("'content_hash' doit être une empreinte SHA-256.")


@dataclass(frozen=True, slots=True)
class EmbeddingProcessingFailure:
    """
    Description d'un bloc dont l'indexation a échoué.
    """

    block_index: int
    error_type: str
    error_message: str


@dataclass(frozen=True, slots=True)
class EmbeddingProcessingResult:
    """
    Résultat de l'indexation d'une transcription.

    Attributes:
        total_blocks: Nombre total de blocs à traiter.
        processed_blocks: Nombre de nouveaux embeddings générés.
        resumed_blocks: Nombre d'embeddings réutilisés depuis la BDD.
        failed_blocks: Nombre de blocs en erreur.
        failures: Détails des erreurs rencontrées.
    """

    total_blocks: int
    processed_blocks: int
    resumed_blocks: int
    failed_blocks: int
    failures: tuple[EmbeddingProcessingFailure, ...] = ()

    def __post_init__(self) -> None:
        """
        Vérifie la cohérence des compteurs.
        """
        counters = (
            self.total_blocks,
            self.processed_blocks,
            self.resumed_blocks,
            self.failed_blocks,
        )

        if any(counter < 0 for counter in counters):
            raise ValueError("Les compteurs d'indexation ne peuvent pas être négatifs.")

        completed_blocks = self.processed_blocks + self.resumed_blocks + self.failed_blocks

        if completed_blocks != self.total_blocks:
            raise ValueError(
                "La somme des blocs traités, repris et échoués doit correspondre au nombre total de blocs."
            )

        if len(self.failures) != self.failed_blocks:
            raise ValueError("Le nombre d'erreurs détaillées doit correspondre à 'failed_blocks'.")

    @property
    def successful_blocks(self) -> int:
        """
        Retourne le nombre total de blocs disponibles.
        """
        return self.processed_blocks + self.resumed_blocks

    @property
    def is_successful(self) -> bool:
        """
        Indique si tous les blocs ont été indexés avec succès.
        """
        return self.failed_blocks == 0

    @property
    def is_partial_success(self) -> bool:
        """
        Indique si seuls certains blocs ont été indexés.
        """
        return self.successful_blocks > 0 and self.failed_blocks > 0
