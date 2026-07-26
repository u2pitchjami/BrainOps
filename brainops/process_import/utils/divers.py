"""
# process/divers.py
"""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path

from langdetect import detect

from brainops.io.read_note import read_note_content
from brainops.io.utils import count_words
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.sql.get_linked.db_get_linked_notes_utils import get_note_lang
from brainops.utils.config import MODEL_EN, MODEL_FR
from brainops.utils.logger import LoggerProtocol, ensure_logger
from brainops.utils.normalization import sanitize_created, sanitize_filename


def hash_content(content: str, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    h.update(content.encode("utf-8"))
    return h.hexdigest()


def rename_file(name: str, note_id: int, *, created: str | None = None, logger: LoggerProtocol | None = None) -> str:
    """
    Renomme un fichier en préfixant par la date (créée ou actuelle), en évitant les collisions.

    Retourne le nouveau chemin.
    """
    logger = ensure_logger(logger, __name__)

    logger.debug("[DEBUG] rename_file → %s", name)

    # Récupère created_at depuis la DB si dispo, sinon now()
    created_at_raw: str | None = created
    try:
        created_str = (
            sanitize_created(created_at_raw, logger=logger) if created_at_raw else datetime.now().strftime("%Y-%m-%d")
        )
        stem_sanitized = sanitize_filename(name, logger=logger)
        new_name = f"{created_str} {stem_sanitized}"

        return new_name
    except Exception as exc:
        raise BrainOpsError("Rennomage fichier KO", code=ErrCode.FILEERROR, ctx={"note_id": note_id}) from exc


def make_relative_link(
    original_path: str | Path,
    filepath: str | Path,
    *,
    logger: LoggerProtocol | None = None,
) -> Path:
    """
    Convertit un chemin absolu (original_path) en chemin relatif à partir du dossier de 'filepath'.

    Retourne un Path relatif utilisable dans un lien Obsidian.
    """
    logger = ensure_logger(logger, __name__)
    orig = Path(str(original_path))
    base = Path(str(filepath)).parent

    if base in orig.parents:
        rel = orig.relative_to(base)
        logger.debug("[DEBUG] relative_path : %s", rel)
        return rel
    raise ValueError(f"Le fichier {orig} est hors du répertoire de base {base}")


def lang_detect(file_path: str | Path, *, logger: LoggerProtocol | None = None) -> str:
    """
    Détecte la langue ('fr', 'en', ...), 'na' si trop court (<50 mots) ou indétectable.
    """
    logger = ensure_logger(logger, __name__)
    content = read_note_content(Path(str(file_path)).as_posix(), logger=logger)
    nb_words = count_words(content=content, logger=logger)

    if nb_words < 50:
        return "na"

    try:
        lang = detect(content)
        logger.debug("[DEBUG] lang_detect: %s (words=%s)", lang, nb_words)
        return "fr" if lang == "fr" else lang
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("[DEBUG] lang_detect exception: %s", exc)
        return "na"


def prompt_name_and_model_selection(
    note_id: int,
    key: str,
    forced_model: str | None = None,
    logger: LoggerProtocol | None = None,
) -> tuple[str, str]:
    """
    Sélectionne (prompt_name, model_ollama) selon la langue de la note.

    - prompt suffixé _en si langue != 'fr'
    - modèle choisi via config (MODEL_FR / MODEL_EN) sauf si forced_model fourni
    """
    logger = ensure_logger(logger, __name__)
    valid_keys = {
        "reformulation",
        "reformulation2",
        "divers",
        "synthese2",
        "add_tags",
        "summary",
        "type",
        "glossaires",
        "glossaires_regroup",
        "synth_translate",
        "add_questions",
        "window_gpt",
    }
    if key not in valid_keys:
        raise ValueError(f"Clé inconnue : {key}")

    lang = get_note_lang(note_id, logger=logger)
    prompt_name = f"{key}_en" if lang != "fr" else key
    model_ollama = forced_model or (MODEL_EN if lang != "fr" else MODEL_FR)
    return prompt_name, model_ollama
