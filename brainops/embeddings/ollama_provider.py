"""
Indexation des paragraphes d'une transcription avec Ollama.
"""

from __future__ import annotations

from brainops.ollama.ollama_call import call_ollama_embedding_with_retry
from brainops.utils.logger import (
    LoggerProtocol,
)


class OllamaEmbeddingProvider:
    """
    Fournisseur d'embeddings utilisant Ollama.
    """

    def embed(
        self,
        *,
        text: str,
        model: str,
        logger: LoggerProtocol,
    ) -> list[float]:
        return call_ollama_embedding_with_retry(
            prompt=text,
            model_ollama=model,
            logger=logger,
        )
