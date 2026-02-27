from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def build_podcast_summary_prompt(
    blocks: Sequence[str] | Sequence[dict[str, Any]],
) -> str:
    """
    Construit un prompt de synthèse adapté à un podcast radio à partir de blocs issus de la transcription.
    """

    intro = (
        "Voici une série d’extraits issus de la transcription d’un podcast radio. "
        "Ces extraits proviennent de différents moments de l’émission "
        "(interventions, échanges, arguments, exemples).\n\n"
        "Le contenu est issu d’un discours oral : il peut contenir des hésitations, "
        "répétitions ou digressions.\n\n"
    )

    def extract_text(b: Any) -> str:
        if isinstance(b, dict) and "text" in b:
            return str(b["text"])
        return str(b)

    parts = [f"Extrait {i + 1} :\n{extract_text(b)}\n" for i, b in enumerate(blocks)]
    content = "\n".join(parts)

    end = (
        "\nÀ partir de ces extraits :\n"
        "- Identifie les thèmes principaux abordés dans l’émission.\n"
        "- Reformule clairement les arguments et idées majeures.\n"
        "- Lorsque c’est identifiable, distingue les positions des différents intervenants.\n"
        "- Mets en évidence les exemples, faits, chiffres ou références importantes.\n"
        "- Supprime les répétitions et reformule le discours oral en style écrit clair.\n\n"
        "Produis une synthèse structurée, hiérarchisée par thèmes de ce podcast audio.\n"
        "La sortie doit être en **français**, structurée en sections lisibles dans **Obsidian** "
        "(titres, sous-parties si pertinent).\n"
        "Ajoute une introduction présentant le contexte et le ou les invités, ainsi qu'une conclusion pertinente."
    )

    return f"{intro}{content}{end}"
