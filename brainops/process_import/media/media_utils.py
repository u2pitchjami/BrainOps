"""
# handlers/process/synthesis.py
"""

from __future__ import annotations

from brainops.utils.logger import LoggerProtocol, ensure_logger


def make_retranscription(
    content: str,
    translate_synth: str | None = None,
    glossary: str | None = None,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Construit le contenu final de la synthèse et l’écrit dans le fichier.

    - synthesis_lines peut être fournis ; sinon on relit le fichier.
    """
    logger = ensure_logger(logger, __name__)
    try:
        # Fallbacks propres
        content_lines = (content or "").strip()

        # titres
        synth_title = "# RETRANSCRIPTION"

        # Blocs optionnels
        # translate_block = format_optional_block("Traduction française", translate_synth)
        glossary_block = format_optional_block("Glossaire", glossary)

        # Assemblage
        blocks = [
            "",
            synth_title,
            "",
            "<!-- BRAINOPS_RETRANSCRIPTION_START -->",
            content_lines,
            "<!-- BRAINOPS_RETRANSCRIPTION_END -->",
        ]
        # Séparateurs facultatifs
        # if translate_block:
        # blocks += ["", "---", "", translate_block]
        if glossary_block:
            blocks += [
                "",
                "---",
                "<!-- BRAINOPS_GLOSSARY_START -->",
                "",
                glossary_block,
                "<!-- BRAINOPS_GLOSSARY_END -->",
            ]

        body_content = "\n".join(blocks).strip()
        # final_synth_body_content = clean_fake_code_blocks(body_content)

        return body_content
    except Exception as exc:  # pylint: disable=broad-except
        # Utiliser logger global si dispo (pas de décorateur ici)
        logger.exception("[ERREUR] make_syntheses : %s", exc)
        raise


def format_optional_block(title: str, content: str | None) -> str:
    """
    Ajoute un titre markdown si le contenu est présent et non vide.
    """
    if content and content.strip():
        return f"## {title}\n\n{content.strip()}"
    return ""
