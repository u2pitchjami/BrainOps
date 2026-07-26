"""check_ollama.py - Vérification de la santé du modèle Ollama."""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.utils.config import MODEL_LARGE_NOTE
from brainops.utils.logger import LoggerProtocol, ensure_logger


def check_ollama_health(model: str = MODEL_LARGE_NOTE, logger: LoggerProtocol | None = None) -> bool:
    """
    Vérifie que le modèle Ollama est opérationnel.

    Renvoie False si l'appel échoue après les retries internes.
    """
    logger = ensure_logger(logger, __name__)
    prompt = "Es-tu opérationnel ? Réponds uniquement par oui ou non."
    try:
        _ = call_ollama_with_retry(prompt, model, logger=logger)
        return True
    except BrainOpsError as error:
        logger.error("Échec du healthcheck Ollama : %s", error)
        return False
