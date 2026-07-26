"""
# header/get_tags_and_summary.py
"""

from __future__ import annotations

import json
import re

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.ollama.ollama_call import OllamaError, call_ollama_with_retry
from brainops.ollama.prompts import PROMPTS
from brainops.process_import.utils.divers import prompt_name_and_model_selection
from brainops.utils.config import MODEL_SUMMARY
from brainops.utils.logger import LoggerProtocol, ensure_logger

_JSON_OBJECT_RE = re.compile(r"\{.*?\}", re.DOTALL)
_JSON_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_TAG_CLEAN_RE = re.compile(r"[:*?\"<>#|'\\]")  # caractères à retirer dans un tag


def _sanitize_tag(tag: str) -> str:
    """
    Nettoie un tag pour l'entête (underscore pour espaces, retire chars interdits).
    """
    t = (tag or "").strip()
    t = _TAG_CLEAN_RE.sub("", t)
    t = "_".join(t.split())
    return t


def _parse_jsonish_tags(response: str) -> list[str]:
    """
    Extrait une liste de tags depuis la réponse LLM.

    - Supporte: bloc ```json ...```, objet {"tags":[...]} ou tableau [...],
    - Renvoie [] si rien d'exploitable.
    """
    text = response or ""

    # 1) bloc entre fences ``` ```
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()

    # 2) objet JSON complet {"tags":[...]}
    m = _JSON_OBJECT_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "tags" in obj and isinstance(obj["tags"], list):
                return [_sanitize_tag(str(t)) for t in obj["tags"] if str(t).strip()]
        except json.JSONDecodeError:
            pass

    # 3) tableau JSON pur [...]
    m = _JSON_ARRAY_RE.search(text)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return [_sanitize_tag(str(t)) for t in arr if str(t).strip()]
        except json.JSONDecodeError:
            pass

    return []


def get_tags_from_ollama(content: str, note_id: int, *, logger: LoggerProtocol | None = None) -> list[str]:
    """
    Interroge Ollama pour générer des tags à partir du contenu.

    Retourne toujours une liste (éventuellement vide).
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] tags ollama : lancement fonction")

    tags: list[str] = []

    try:
        prompt_name, model_ollama = prompt_name_and_model_selection(note_id, key="add_tags", logger=logger)
        prompt_tpl = PROMPTS.get(prompt_name)
        if not prompt_tpl:
            logger.error("[ERREUR] Prompt '%s' introuvable dans PROMPTS.", prompt_name)
            return []
        prompt = prompt_tpl.format(content=content)
        logger.debug("[DEBUG] tags ollama : prompt_name=%s model=%s", prompt_name, model_ollama)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Construction du prompt tags : %s", exc)
        return []

    try:
        logger.debug("[DEBUG] tags ollama : appel modèle…")
        response = call_ollama_with_retry(prompt, model_ollama, logger=logger)
        logger.debug("[DEBUG] tags ollama : réponse récupérée (%d chars)", len(response or ""))

        tags = _parse_jsonish_tags(response)
        if not tags:
            logger.warning("[WARN] Aucun JSON exploitable trouvé dans la réponse pour les tags.")
            return []

        # dédoublonnage et filtrage des vides
        uniq = []
        seen = set()
        for t in tags:
            if t and t not in seen:
                uniq.append(t)
                seen.add(t)
        return uniq

    except OllamaError:
        logger.error("[ERROR] Appel Ollama échoué pour les tags (OllamaError).")
        return []
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Parsing tags : %s", exc)
        return []


def get_summary_from_ollama(content: str, note_id: int, *, logger: LoggerProtocol | None = None) -> str:
    """
    Génère un résumé automatique avec Ollama.
    - Utilise le prompt 'summary' (via prompt_name_and_model_selection pour le nom),
      et le modèle paramétré dans ton code (obook_summary).
    - Retourne le texte entre 'TEXT START' et 'TEXT END' s'il est présent, sinon la réponse brute.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] résumé ollama : lancement fonction")

    try:
        prompt_name, _ = prompt_name_and_model_selection(note_id, key="summary", logger=logger)
        prompt_tpl = PROMPTS.get(prompt_name)
        if not prompt_tpl:
            logger.error("[ERREUR] Prompt '%s' introuvable dans PROMPTS.", prompt_name)
            raise BrainOpsError("Prompt absent KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id})
        prompt = prompt_tpl.format(content=content)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Construction du prompt résumé : %s", exc)
        raise BrainOpsError("Prompt KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc

    # modèle voulu par ton implémentation actuelle
    model_ollama = MODEL_SUMMARY

    try:
        logger.debug("[DEBUG] résumé ollama : appel modèle…")
        response = call_ollama_with_retry(prompt, model_ollama, logger=logger)
        if not response:
            raise BrainOpsError("Ollama KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id})

        # Nettoyage: chercher 'TEXT START ... TEXT END'
        m = re.search(r"TEXT START(.*?)TEXT END", response, re.DOTALL | re.IGNORECASE)
        if m:
            summary = m.group(1).strip()
            logger.debug(
                "[DEBUG] summary ollama : extrait entre balises (%d chars)",
                len(summary),
            )
            return summary

        logger.debug("[DEBUG] summary ollama : pas de balise, retour brut.")
        return response.strip()

    except OllamaError as exc:
        logger.error("[ERROR] Appel Ollama échoué pour le résumé (OllamaError).")
        raise BrainOpsError("Ollama KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
    except Exception as exc:
        logger.exception("[ERREUR] résumé ollama : %s", exc)
        raise BrainOpsError("Ollama KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
