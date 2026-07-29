"""
Construction des prompts d'analyse et de synthèse.

Module : process/embeddings_utils.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brainops.models.note_context import NoteContext


Block = str | Mapping[str, Any]


def _extract_block_text(block: Block) -> str:
    """
    Extrait le texte d'un bloc sélectionné.

    Args:
        block: Bloc textuel ou mapping contenant une clé ``text``.

    Returns:
        Texte nettoyé du bloc.

    Raises:
        ValueError: Si le bloc ne contient aucun texte exploitable.
    """
    if isinstance(block, str):
        text = block.strip()
    else:
        raw_text = block.get("text")
        text = str(raw_text).strip() if raw_text is not None else ""

    if not text:
        raise ValueError("Un bloc sélectionné ne contient aucun texte exploitable.")

    return text


def _build_blocks_section(blocks: Sequence[Block]) -> str:
    """
    Construit la section contenant les extraits sélectionnés.

    Les blocs restent dans l'ordre fourni par le pipeline.
    """
    if not blocks:
        raise ValueError("Impossible de construire le prompt : aucun bloc n'a été fourni.")

    formatted_blocks = [
        (f'<bloc id="{index}">\n{_extract_block_text(block)}\n</bloc>') for index, block in enumerate(blocks, start=1)
    ]

    return "\n\n".join(formatted_blocks)


def _build_list_section(title: str, values: Sequence[str]) -> str:
    """
    Construit une section Markdown à partir d'une liste de consignes.

    Les valeurs vides sont ignorées.
    """
    cleaned_values = [value.strip() for value in values if value.strip()]

    if not cleaned_values:
        return ""

    items = "\n".join(f"- {value}" for value in cleaned_values)
    return f"### {title}\n{items}"


def _build_analysis_profile_section(ctx: NoteContext) -> str:
    """
    Construit les paramètres d'analyse issus du profil résolu.

    ``ctx.analysis`` contient déjà la combinaison du profil YAML et des
    éventuelles personnalisations propres à la note ou au média.
    """
    analysis = ctx.analysis
    sections = [
        f"### Profil\n{analysis.profile}",
    ]

    if analysis.objective:
        sections.append(f"### Objectif\n{analysis.objective.strip()}")

    if analysis.perspective:
        sections.append(f"### Perspective\n{analysis.perspective.strip()}")

    instructions_section = _build_list_section(
        "Consignes d'analyse",
        analysis.instructions,
    )
    if instructions_section:
        sections.append(instructions_section)

    reflection_section = _build_list_section(
        "Questions guidant l'analyse",
        analysis.reflection_questions,
    )
    if reflection_section:
        sections.append(reflection_section)

    return "\n\n".join(sections)


def _build_media_context_section(ctx: NoteContext) -> str:
    """
    Construit le contexte éditorial propre au contenu.

    Le nom exact de l'attribut pourra être adapté lors de la refonte de
    ``Media``. Ici, l'hypothèse est que le contexte final résolu est placé
    dans ``ctx.analysis.context``.
    """

    if not ctx.media or not ctx.media.editorial_context or not ctx.media.editorial_context.strip():
        return ""

    return f"""
        ## Contexte éditorial

        Le texte suivant présente le contexte particulier du contenu analysé.

        Utilise-le pour identifier le sujet, les intervenants, le cadre et les
        questions annoncées. Ne considère pas ses formulations comme des conclusions
        démontrées. Les extraits du contenu restent la source principale.

        <context>
        {ctx.media.editorial_context.strip()}
        </context>
        """.strip()


def build_struct_media_prompt(
    profile_section: str,
    media_context_section: str | None,
    blocks_section: str,
) -> str:
    """
    Construit le prompt générique de synthèse.

    Le comportement du prompt est piloté par ``ctx.analysis`` et non par le
    type technique de la source.

    Args:
        blocks: Blocs retenus par la stratégie de sélection.
        ctx: Contexte métier complet de la note.

    Returns:
        Prompt prêt à être envoyé au modèle.

    Raises:
        ValueError: Si aucun bloc exploitable n'est fourni.
    """

    optional_context = f"\n\n{media_context_section}" if media_context_section else ""

    return f"""
# Rôle

Tu es un rédacteur documentaire chargé de transformer une transcription
orale ou un contenu brut en notes de lecture structurées.

Ton objectif n'est pas de résumer le contenu, mais de le rendre clair,
agréable à lire et facile à exploiter ultérieurement.

# Mission

Analyse les extraits fournis comme les différentes parties d'un même contenu.
Construis un document fidèle et structuré à partir des extraits fournis en appliquant le profil d'analyse
ci-dessous.

Les extraits ont été sélectionnés automatiquement. Ils peuvent être
discontinus et ne représentent pas nécessairement l'intégralité du contenu.

N'invente pas les éléments manquants et ne transforme pas une hypothèse,
une interprétation ou une opinion en fait établi.

## Paramètres d'analyse

{profile_section}{optional_context}

## Extraits à analyser

{blocks_section}

# Règles de traitement

- Identifie les idées principales et leurs relations.
- Réorganise les informations pour améliorer la lecture.
- Conserve autant que possible la progression logique du contenu.
- Ne fusionne pas plusieurs idées distinctes si cela fait perdre de
  l'information.
- Distingue les faits, les interprétations et les opinions lorsque cela est
  pertinent.
- Préserve les nuances, réserves, désaccords et incertitudes.
- Attribue les positions aux bons intervenants lorsque cette information est
  disponible.
- Conserve les exemples, chiffres, références et formulations significatives.
- Signale explicitement lorsqu'une information reste ambiguë ou insuffisamment
  étayée.
- Évite les répétitions et les reformulations artificielles.
- N'ajoute aucune information extérieure au contenu fourni.
- Utilise les questions guidant l'analyse comme des axes d'attention, sans
  nécessairement y répondre sous forme de questions-réponses.

Tu peux :

- supprimer les hésitations,
- supprimer les répétitions inutiles,
- reformuler les phrases maladroites,
- corriger la syntaxe.

Tu ne dois pas :

- raccourcir volontairement le contenu,
- supprimer une idée importante,
- fusionner plusieurs arguments différents,
- inventer des liens qui ne sont pas explicitement présents.

# Format attendu

Produis un document en français, au format Markdown
compatible avec Obsidian.

Structure la réponse avec des titres de niveau 2 et 3 lorsque cela améliore la
lecture.
Tu peux ajouter des paragraphes, des listes ou des tableaux si cela est pertinent.

N'ajoute pas de préambule tel que « Voici la synthèse ».
N'ajoute pas de conclusion générique ou décorative.
""".strip()


def build_tags_prompt(
    media_context_section: str | None,
    blocks_section: str,
) -> str:
    """
    Construit le prompt générique pour les tags.

    Args:
        blocks: Blocs retenus par la stratégie de sélection.
        ctx: Contexte métier complet de la note.

    Returns:
        Prompt prêt à être envoyé au modèle.

    Raises:
        ValueError: Si aucun bloc exploitable n'est fourni.
    """

    optional_context = f"{media_context_section}\n\n" if media_context_section else ""

    return f"""
    Vous êtes un bot dans une application de lecture différée et votre rôle est de contribuer au balisage automatique.
    DÉBUT DU CONTENU
    {optional_context}{blocks_section}
    FIN DU CONTENU

    Instructions :

    1. Lisez le contenu.
    2. Suggérez des tags pertinentes qui décrivent ses thèmes, sujets et idées principales. Règles :
    - Utilisez une variété de tags, incluant des catégories générales, des mots-clés spécifiques\
        et d'éventuels sous-genres.
    - Les tags doivent être en français.
    - S'il s'agit d'un site web connu, vous pouvez également inclure une balise pour le site.\
    Si la balise n'est pas suffisamment générique, ne l'incluez pas.
    - Le contenu peut inclure des textes relatifs au consentement aux cookies,\
        à la publicité et à la politique de confidentialité. \
        ignorez-les lors du balisage.
    - Visez 3 à 5 tags.
    - Si un matériel et/ou un logiciel spécifique est utilisé,\
        ajoutez des tags avec leurs noms.
    - S'il n'y a pas de tags pertinentes, laissez le tableau vide.
    3. Les tags doivent être renvoyées au **format JSON strict**. 4. N’utilisez **pas** YAML,\
    Markdown, listes à puces ni aucune autre mise en forme.
    5. Retournez **uniquement** l’objet JSON avec la clé « tags » et un tableau de chaînes de caractères comme valeur.
    6. **N’incluez **aucune** explication, aucun titre ni aucun texte supplémentaire dans la réponse.
    7. N’ajoutez **aucun** élément commençant par `#` (hashtags ou titres) ou `-` (listes à puces ou listes).
    """.strip()


def build_glossary_prompt(
    media_context_section: str | None,
    blocks_section: str,
) -> str:
    """
    Construit le prompt générique pour le glossaire.

    Args:
        blocks: Blocs retenus par la stratégie de sélection.
        ctx: Contexte métier complet de la note.

    Returns:
        Prompt prêt à être envoyé au modèle.

    Raises:
        ValueError: Si aucun bloc exploitable n'est fourni.
    """
    optional_context = f"{media_context_section}\n\n" if media_context_section else ""

    return f"""
    Tu es un assistant chargé d'extraire un glossaire à partir d'une section de texte.

    Analyse le texte ci-dessous et identifie les **termes spécifiques, techniques ou récurrents**.
    Pour chaque terme important, fournis une **brève définition claire** basée uniquement sur le contexte.

    **Ta mission :**
    - Fusionne les définitions identiques ou similaires
    - Garde la version la plus claire et pertinente de chaque définition
    - Trie les entrées par ordre alphabétique
    - Ignore les doublons ou les entrées trop vagues
    - le résultat ne doit pas contenir plus de 5 à 10 entrées
    - Le contenu doit être obligatoirement en **français**.

    **Format attendu :**
    - Terme : définition
    - Terme : définition

    Ne définis que les termes réellement importants ou ambigus. Ignore les termes trop génériques.

    Texte à analyser :
    {optional_context}{blocks_section}
    """.strip()


def build_summary_prompt(
    media_context_section: str | None,
    blocks_section: str,
) -> str:
    """
    Construit le prompt générique pour les summary.

    Args:
        blocks: Blocs retenus par la stratégie de sélection.
        ctx: Contexte métier complet de la note.

    Returns:
        Prompt prêt à être envoyé au modèle.

    Raises:
        ValueError: Si aucun bloc exploitable n'est fourni.
    """
    optional_context = f"{media_context_section}\n\n" if media_context_section else ""

    return f"""
    Résume le texte suivant de façon concise en te concentrant sur :
    - les arguments principaux,
    - les éléments de preuve importants,
    - et les conclusions significatives.

    Consignes :
    1. Présente le résumé sous forme de puces (bullet points).
    2. Maximum 5 phrases au total.
    3. Ne commence ni ne termine par des phrases introductives ou conclusives.
    5. Ne retourne **que le résumé**, sans titre, explication ou formatage supplémentaire.
    6. Le résumé doit être en **français**.

    Voici le texte à analyser :
    {optional_context}{blocks_section}
    """.strip()


def build_prompts_main(
    blocks: Sequence[Block],
    ctx: NoteContext,
) -> tuple[str, str, str, str]:
    """
    Main pour la construction de prompts à partir d'embeddings.
    """
    profile_section = _build_analysis_profile_section(ctx)
    media_context_section = _build_media_context_section(ctx)
    blocks_section = _build_blocks_section(blocks)

    struct_media_prompt = build_struct_media_prompt(profile_section, media_context_section, blocks_section)
    glossary_prompt = build_glossary_prompt(media_context_section, blocks_section)
    tags_prompt = build_tags_prompt(media_context_section, blocks_section)
    summary_prompt = build_summary_prompt(media_context_section, blocks_section)

    return struct_media_prompt, glossary_prompt, tags_prompt, summary_prompt
