"""
Split method.
"""

from __future__ import annotations

import re

from brainops.utils.logger import LoggerProtocol, ensure_logger

_QA_LINE = re.compile(r"^\[T\d+\]\[(user|assistant)\]:", re.M)


def _normalize_newlines(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    # espace/onglets en fin de ligne → retirés
    s = re.sub(r"[ \t]+$", "", s, flags=re.M)
    return s


def _split_on_blank_lines(s: str) -> list[str]:
    # Coupe sur ≥ 1 ligne vide ; garde l’ordre ; filtre les vides
    return [p.strip() for p in re.split(r"\n{2,}", s) if p.strip()]


def _looks_like_qa_block(block: str) -> bool:
    # doit contenir au moins une ligne user et une assistant
    has_user = re.search(r"^\[T\d+\]\[user\]:", block, re.M) is not None
    has_asst = re.search(r"^\[T\d+\]\[assistant\]:", block, re.M) is not None
    return has_user and has_asst


def split_qa_paragraphs(
    text: str, *, logger: LoggerProtocol | None = None, min_chars: int = 240, max_chars: int = 2000
) -> list[str]:
    """
    - Suppose un fichier *préparé* où chaque bloc Q→R est séparé par une ligne vide.
    - Valide les blocs; recolle les fragments trop courts; coupe les trop longs (rare si pair_chunks fait son job).
    """
    logger = ensure_logger(logger, __name__)
    s = _normalize_newlines(text)

    # 1) Détection rapide : si aucun pattern [T..][role] → ce n'est pas un fichier Q/R préparé.
    if not _QA_LINE.search(s):
        logger.warning("[SPLIT] qa_paragraphs: aucun marqueur [T#][role] détecté; retour 'texte entier' en 1 bloc.")
        return [s.strip()] if s.strip() else []

    # 2) Split brut sur lignes vides
    blocks = _split_on_blank_lines(s)
    if not blocks:
        return []

    # 3) Filtrage & réparation légère
    fixed: list[str] = []
    buf = ""
    for b in blocks:
        if not _looks_like_qa_block(b):
            # fragment isolé (ex: juste une relance) → accumuler
            buf = f"{buf}\n\n{b}".strip() if buf else b
            continue

        # flush éventuel
        if buf:
            merged = f"{buf}\n\n{b}"
            if _looks_like_qa_block(merged):
                b = merged
                buf = ""
            else:
                # on pousse le buffer comme bloc séparé s'il est long
                if len(buf) >= min_chars:
                    fixed.append(buf)
                else:
                    # sinon on l'accole au bloc courant
                    b = f"{buf}\n\n{b}"
                buf = ""

        # bornes de sécurité caractères
        if len(b) > max_chars:
            # coupe proprement sur double newline ou fin de phrase
            parts = re.split(r"(\n{2,}|(?<=[\.\!\?])\s+(?=\[T\d+\]\[(user|assistant)\]:))", b)
            chunk = ""
            for seg in parts:
                if not seg or seg.isspace():
                    continue
                cand = f"{chunk}{seg}"
                if len(cand) <= max_chars:
                    chunk = cand
                else:
                    fixed.append(chunk.strip())
                    chunk = seg
            if chunk.strip():
                fixed.append(chunk.strip())
        else:
            fixed.append(b)

    if buf:
        # il reste un buffer en fin de boucle
        fixed.append(buf)

    # 4) Dernier filtre: enlever les miettes trop courtes
    result = [x for x in fixed if len(x) >= min_chars]
    logger.info("[SPLIT] qa_paragraphs → %d blocs (init=%d)", len(result), len(blocks))
    return result
