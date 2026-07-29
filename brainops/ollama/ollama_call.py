"""
# ollama/ollama_call.py
"""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.process_import.utils.gpu_guard import get_ollama_base_url
from brainops.utils.config import MODEL_EMBEDDINGS, OLLAMA_EMBEDDINGS_ENDPOINT, OLLAMA_TIMEOUT
from brainops.utils.logger import LoggerProtocol, ensure_logger


class OllamaError(Exception):
    """
    Exception spécifique pour les erreurs Ollama.
    """


def call_ollama_with_retry(
    prompt: str,
    model_ollama: str,
    retries: int = 5,
    delay: int = 10,
    *,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Appelle Ollama avec 'retries' essais.

    - Pour les modèles d'embedding ('nomic-embed-text:latest'), bascule sur get_embedding()
      mais retourne une string JSONifiée de l'embedding par compat, ou None si échec.
    """
    import time

    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] call_ollama_with_retry model=%s", model_ollama)

    for attempt in range(retries):
        try:
            base_url = get_ollama_base_url(model_name=model_ollama)
            if model_ollama == MODEL_EMBEDDINGS:
                endpoint = f"{base_url}/api/embeddings"
                emb = get_embedding(endpoint, prompt, model_ollama, logger=logger)
                return json.dumps(emb)
            endpoint = f"{base_url}/api/generate"
            return ollama_generate(endpoint, prompt, model_ollama, logger=logger)
        except OllamaError as exc:
            logger.warning("[WARNING] Tentative %d/%d échouée : %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                logger.info("[INFO] Nouvelle tentative dans %d secondes…", delay)
                time.sleep(delay)
            else:
                logger.error("[ERREUR] Ollama ne répond pas après %d tentatives.", retries)
                raise BrainOpsError(
                    "KO récup ou création subcatg", code=ErrCode.DB, ctx={"name": "call_ollama_with_retry"}
                ) from exc
    raise BrainOpsError("KO récup ou création subcatg", code=ErrCode.DB, ctx={"name": "call_ollama_with_retry"})


def call_ollama_embedding_with_retry(
    prompt: str,
    model_ollama: str,
    retries: int = 5,
    delay: int = 10,
    *,
    logger: LoggerProtocol | None = None,
) -> list[float]:
    """
    Appelle un modèle d'embedding Ollama avec gestion des tentatives.
    """
    logger = ensure_logger(logger, __name__)

    last_error: Exception | None = None
    base_url = get_ollama_base_url(model_name=model_ollama)
    for attempt in range(1, retries + 1):
        try:
            return get_embedding(
                endpoint=f"{base_url}{OLLAMA_EMBEDDINGS_ENDPOINT}",
                prompt=prompt,
                model_ollama=model_ollama,
                logger=logger,
            )
        except BrainOpsError as exc:
            last_error = exc

            logger.warning(
                "Échec embedding Ollama : modèle=%s tentative=%d/%d",
                model_ollama,
                attempt,
                retries,
            )

            if attempt < retries:
                time.sleep(delay)

    raise BrainOpsError(
        "Échec définitif de l'embedding Ollama.",
        code=ErrCode.OLLAMA,
        ctx={
            "model": model_ollama,
            "retries": retries,
        },
    ) from last_error


def ollama_generate(endpoint: str, prompt: str, model_ollama: str, *, logger: LoggerProtocol | None = None) -> str:
    """
    Appel texte → texte sur le endpoint GENERATE (stream).

    Concatène les fragments 'response' du flux JSONL.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] ollama_generate model=%s url=%s", model_ollama, endpoint)

    payload: dict[str, Any] = {
        "model": model_ollama,
        "prompt": prompt,
        "options": {"num_predict": -1, "num_ctx": 16384},
    }

    try:
        with requests.post(
            endpoint,
            json=payload,
            stream=True,
            timeout=OLLAMA_TIMEOUT,
        ) as resp:
            if resp.status_code == 404 or None:
                raise BrainOpsError(
                    "Modèle introuvable sur Ollama (404)", code=ErrCode.OLLAMA, ctx={"status": resp.status_code}
                )
            if resp.status_code in (500, 503):
                raise BrainOpsError("Ollama indisponible)", code=ErrCode.OLLAMA, ctx={"status": resp.status_code})
            resp.raise_for_status()

            full: list[str] = []
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    piece = obj.get("response", "")
                    if piece:
                        full.append(piece)
                except json.JSONDecodeError:
                    # tolérant : parfois la ligne n'est pas JSON, on concatène brut
                    full.append(str(raw))

            text = "".join(full).strip()
            if not text:
                logger.warning("[WARNING] 🚨 Réponse Ollame vide")
                raise BrainOpsError("Ollama indisponible)", code=ErrCode.OLLAMA, ctx={"status": resp.status_code})
    except requests.exceptions.Timeout as exc:
        raise BrainOpsError(
            "Timeout sur l'appel generate", code=ErrCode.OLLAMA, ctx={"status": resp.status_code}
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise BrainOpsError(
            "Connexion à Ollama impossible (Docker HS ?)", code=ErrCode.OLLAMA, ctx={"status": resp.status_code}
        ) from exc
    except requests.HTTPError as exc:
        raise BrainOpsError("HTTPError Ollama", code=ErrCode.OLLAMA, ctx={"status": resp.status_code}) from exc
    return text


def get_embedding(
    endpoint: str, prompt: str, model_ollama: str, *, logger: LoggerProtocol | None = None
) -> list[float]:
    """
    Appel texte → embedding sur le endpoint EMBEDDINGS.

    Retourne la liste des floats, ou None en cas d'échec.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] get_embedding model=%s url=%s", model_ollama, endpoint)

    payload: dict[str, Any] = {
        "model": model_ollama,
        "prompt": prompt,
        "options": {"num_predict": -1, "num_ctx": 4096},
        "keep_alive": 0,
    }

    try:
        resp = requests.post(endpoint, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # format attendu: {"embedding": [...]}
        emb = data.get("embedding", [])
        if not emb:
            logger.warning("[WARNING] 🚨 Embedding vide !")
            raise BrainOpsError("Embedding vide)", code=ErrCode.OLLAMA, ctx={"status": resp.status_code})
        # S'assurer que c'est bien une liste de floats
        return [float(x) for x in emb]
    except requests.exceptions.Timeout as exc:
        raise BrainOpsError(
            "Timeout sur l'appel generate", code=ErrCode.OLLAMA, ctx={"status": resp.status_code}
        ) from exc
    except Exception as exc:
        raise BrainOpsError("Ollama KO", code=ErrCode.OLLAMA, ctx={"status": resp.status_code}) from exc
