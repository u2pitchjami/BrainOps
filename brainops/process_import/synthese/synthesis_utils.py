"""
# handlers/process/synthesis.py
"""

from __future__ import annotations

from brainops.ollama.ollama_utils import large_or_standard_note
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger
from brainops.utils.normalization import clean_fake_code_blocks


@with_child_logger
def make_translate(content: str, note_id: int, logger: LoggerProtocol | None = None) -> str | None:
    """
    make_translate _summary_

    _extended_summary_

    Args:
        filepath (str | Path): _description_
        note_id (int): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        Optional[str]: _description_
    """
    logger = ensure_logger(logger, __name__)
    prompt_key = "synth_translate"
    return large_or_standard_note(
        content=content,
        source="synth_translate",
        process_mode="standard_note",
        prompt_key=prompt_key,
        note_id=note_id,
        write_file=False,
        logger=logger,
    )


@with_child_logger
def make_questions(
    note_id: int,
    content: str | None,
    logger: LoggerProtocol | None = None,
) -> str | None:
    """
    make_questions _summary_

    _extended_summary_

    Args:
        filepath (str | Path): _description_
        note_id (int): _description_
        content (Optional[str]): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        Optional[str]: _description_
    """
    logger = ensure_logger(logger, __name__)
    prompt_key = "add_questions"
    return large_or_standard_note(
        content=content or "",
        source="add_questions",
        process_mode="standard_note",
        prompt_key=prompt_key,
        note_id=note_id,
        write_file=False,
        logger=logger,
    )


@with_child_logger
def make_glossary(content: str, note_id: int, logger: LoggerProtocol | None = None) -> str:
    """
    make_glossary _summary_

    _extended_summary_

    Args:
        filepath (str | Path): _description_
        note_id (int): _description_
        logger (LoggerProtocol | None, optional): _description_. Defaults to None.

    Returns:
        str: _description_
    """
    # 1/2 : extraction brute
    logger = ensure_logger(logger, __name__)
    prompt_key = "glossaires"
    glossary_sections = large_or_standard_note(
        content=content,
        note_id=note_id,
        source="glossary",
        process_mode="large_note",
        max_chars=3800,
        max_tokens=1500,
        prompt_key=prompt_key,
        write_file=False,
        logger=logger,
    )
    if not glossary_sections:
        # On retourne chaîne vide (le bloc sera simplement omis)
        return ""

    # 2/2 : regroupement
    prompt_key = "glossaires_regroup"
    final_glossary = large_or_standard_note(
        note_id=note_id,
        content=glossary_sections,
        source="glossary_regroup",
        process_mode="standard_note",
        prompt_key=prompt_key,
        write_file=False,
        logger=logger,
    )
    return final_glossary or ""


@with_child_logger
def make_syntheses(
    note_id: int,
    original_path: str,
    translate_synth: str | None = None,
    glossary: str | None = None,
    questions: str | None = None,
    content_lines: str | None = None,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Construit le contenu final de la synthèse et l’écrit dans le fichier.

    - content_lines peut être fournis ; sinon on relit le fichier.
    """
    logger = ensure_logger(logger, __name__)
    try:
        # Fallbacks propres
        content_lines = (content_lines or "").strip()

        # Lien vers la note originale
        original_link = f"[[{original_path}|Voir la note originale]]"

        # Blocs optionnels
        # translate_block = format_optional_block("Traduction française", translate_synth)
        glossary_block = format_optional_block("Glossaire", glossary)
        questions_block = format_optional_block("Questions", questions)

        # Assemblage
        blocks = [original_link, "", content_lines]
        # Séparateurs facultatifs
        # if translate_block:
        # blocks += ["", "---", "", translate_block]
        if glossary_block:
            blocks += ["", "---", "", glossary_block]
        if questions_block:
            blocks += ["", "---", "", questions_block]

        body_content = "\n".join(blocks).strip()
        final_synth_body_content = clean_fake_code_blocks(body_content)

        return final_synth_body_content
    except Exception as exc:  # pylint: disable=broad-except
        # Utiliser logger global si dispo (pas de décorateur ici)
        logger.exception("[ERREUR] make_syntheses(%s) : %s", note_id, exc)
        raise


def format_optional_block(title: str, content: str | None) -> str:
    """
    Ajoute un titre markdown si le contenu est présent et non vide.
    """
    if content and content.strip():
        return f"## {title}\n\n{content.strip()}"
    return ""
