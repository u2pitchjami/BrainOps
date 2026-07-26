# """
# # process/embeddings_utils.py
# """

# from __future__ import annotations

# from collections.abc import Sequence
# from typing import Any

# from brainops.utils.logger import LoggerProtocol, ensure_logger

# def build_summary_prompt_gpt(
#     blocks: Sequence[str] | Sequence[dict[str, Any]],
#     structure: str = "brainops",
#     require_json: bool = False,
#     logger: LoggerProtocol | None = None,
# ) -> str:
#     """
#     Construit un prompt de synthèse robuste pour conversations GPT "chargées".

#     - structure="brainops": note Obsidian structurée (sections fixes + tags)
#     - require_json=True: demande un JSON structuré (si tu veux post-traiter)
#     Accepte liste de str ou liste de dicts {"text":..., "score":..., "idx":...}
#     """
#     logger = ensure_logger(logger, __name__)

#     def extract_text_and_meta(b: Any) -> tuple[str, str]:
#         if isinstance(b, dict):
#             txt = str(b.get("text", ""))
#             bid = f"B{b.get('idx', '')}".strip()
#             sc = b.get("score")
#             meta = f"[{bid}{' score=' + f'{sc:.4f}' if isinstance(sc, float) else ''}]"
#             return txt, meta
#         return str(b), ""

#     intro_rules_md = (
#         "Tu es un **rapporteur technique**. À partir d’extraits (retrieval par embeddings), "
#         "produis une **note Obsidian** claire, actionnable et traçable, **sans inventer**.\n"
#         "- Si une info est absente/incertaine, écris `N/A`.\n"
#         "- Classe précisément : problèmes, hypothèses, tentatives (succès/échec/partiel),\
#         contournements, décisions, TODO (P1..P3, owner, due), insights, risques, questions ouvertes.\n"
#         "- Ajoute des tags #: #bug #solution #todo #improvement #note là où pertinent.\n"
#         "- Conclus par **Sources** listant les IDs de blocs utilisés.\n"
#     )

#     intro_rules_json = (
#         "Tu es un **consolidateur**. À partir des extraits fournis, retourne un JSON strict UTF-8 "
#         "Voici des extraits importants d'une note. Résume-les de façon concise et claire.\n\n"
#     )

#     header = (
#         intro_rules_json
#         if require_json
#         else intro_rules_md + "\n**Structure attendue (Markdown)** :\n"
#         "1) Résumé exécutif\n"
#         "2) Contexte\n"
#         "3) Problèmes (#bug)\n"
#         "4) Pistes & Tentatives (succès/échec/partiel)\n"
#         "5) Solutions/Contournements (#solution)\n"
#         "6) Décisions\n"
#         "7) TODO priorisés (#todo)\n"
#         "8) Insights (#improvement #note)\n"
#         "9) Risques\n"
#         "10) Questions ouvertes\n"
#         "11) Timeline (si dispo)\n"
#         "12) Sources (IDs de blocs)\n"
#         "\n**Rappels** :\n"
#         "- Aucune invention; cite les éléments par ID de bloc (ex: B12).\n"
#         "- Listes concises, verbes d’action. Sortie en **français**.\n"
#     )

#     parts: list[str] = []
#     used_ids: list[str] = []
#     for i, b in enumerate(blocks):
#         txt, meta = extract_text_and_meta(b)
#         bid = meta.split()[0].strip("[]") if meta else f"B{i + 1}"
#         used_ids.append(bid)
#         parts.append(f"### {bid}\n{txt}\n")

#     content = "\n".join(parts)
#     footer = (
#         "\nConsignes de sortie :\n"
#         "- Fourni **uniquement** le Markdown final (avec sections) lisible dans Obsidian.\n"
#         "- Termine par une section `## Sources` listant les IDs de blocs utilisés.\n"
#         if not require_json
#         else "\nConsignes de sortie :\n- Retourne **uniquement** le JSON demandé, pas de texte hors JSON.\n"
#     )
#     return f"{header}\n\nExtraits fournis :\n\n{content}\n{footer}"
