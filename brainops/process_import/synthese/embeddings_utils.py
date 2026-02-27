"""
# process/embeddings_utils.py
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics.pairwise import cosine_similarity

from brainops.sql.temp_blocs.db_embeddings_temp_blocs import get_blocks_and_embeddings_by_note
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger

MODES = {
    "quick": {"ratio": 0.20, "use_mmr": True, "mmr_lambda": 0.8},
    "standard": {"ratio": 0.30, "use_mmr": True, "mmr_lambda": 0.7},
    "audit": {"ratio": 0.50, "use_mmr": True, "mmr_lambda": 0.6},
    "gpt": {"ratio": 0.45, "use_mmr": True, "mmr_lambda": 0.6},
    "podcast": {"ratio": 0.30, "use_mmr": True, "mmr_lambda": 0.3},
}


def select_top_blocks_by_mode(
    content: str,
    note_id: int,
    mode_def: str = "standard",
    *,
    logger: LoggerProtocol | None = None,
    **overrides: float | bool,
) -> list[dict[str, Any]] | list[str]:
    """
    Wrapper pratique pour appliquer MODES et permettre des overrides:
    ex: select_top_blocks_by_mode(note_id, "audit", ratio=0.55)
    """
    logger = ensure_logger(logger, __name__)
    logger.debug("[DEBUG] select_top_blocks_by_mode mode: %s", mode_def)

    cfg = MODES.get(mode_def, MODES["standard"]).copy()
    logger.debug("[DEBUG] select_top_blocks_by_mode cfg: %s", cfg)
    cfg.update(overrides)  # ex: ratio=0.55 locale
    logger.info("[SELECT] mode=%s cfg=%s", mode_def, cfg)

    return select_top_blocks(
        note_id=note_id,
        ratio=float(cfg["ratio"]),
        return_scores=bool(cfg.get("return_scores", True)),
        use_mmr=bool(cfg["use_mmr"]),
        mmr_lambda=float(cfg["mmr_lambda"]),
        logger=logger,
    )


def _mmr_select(
    query_vec: NDArray[np.float64],
    doc_matrix: NDArray[np.float64],
    top_k: int,
    lambda_mult: float = 0.7,
) -> list[int]:
    """
    Sélectionne top_k indices par MMR (Maximal Marginal Relevance).

    - lambda_mult proche de 1 = pertinence, proche de 0 = diversité.
    """
    sims_to_query = cosine_similarity(query_vec.reshape(1, -1), doc_matrix)[0]  # (m,)
    selected: list[int] = []
    candidates = set(range(doc_matrix.shape[0]))

    while candidates and len(selected) < top_k:
        if not selected:
            i = int(np.argmax(sims_to_query))
            selected.append(i)
            candidates.remove(i)
            continue

        # diversité: max similarité à un déjà sélectionné
        selected_matrix = doc_matrix[selected]
        sims_to_selected = cosine_similarity(doc_matrix[list(candidates)], selected_matrix)
        max_sim_to_selected = sims_to_selected.max(axis=1)  # (|candidats|,)

        cand_indices = np.array(list(candidates))
        mmr_scores = lambda_mult * sims_to_query[cand_indices] - (1 - lambda_mult) * max_sim_to_selected
        best_idx = int(cand_indices[np.argmax(mmr_scores)])
        selected.append(best_idx)
        candidates.remove(best_idx)

    return selected


@with_child_logger
def select_top_blocks(
    note_id: int,
    N: int | None = None,
    ratio: float = 0.3,
    return_scores: bool = False,
    *,
    logger: LoggerProtocol | None = None,
    use_mmr: bool = True,
    mmr_lambda: float = 0.7,
) -> list[dict[str, Any]] | list[str]:
    """
    Variante MMR (par défaut) pour obtenir un mix pertinence/diversité.

    Retourne soit [{"text","score"}], soit ["text", ...] pour compatibilité.
    """
    logger = ensure_logger(logger, __name__)
    logger.debug(
        "[DEBUG] select_top_blocks(note_id=%s, N=%s, ratio=%.2f, MMR=%s, lambda=%.2f)",
        note_id,
        N,
        ratio,
        use_mmr,
        mmr_lambda,
    )

    blocks, embeddings = get_blocks_and_embeddings_by_note(note_id, logger=logger)
    if not blocks or not embeddings:
        logger.warning("[SELECT] Aucun bloc/embedding (note_id=%s).", note_id)
        return []

    total_blocks = len(blocks)
    logger.debug("[DEBUG] select_top_blocks(total_blocks=%s)", total_blocks)
    if N is None:
        N = max(1, int(total_blocks * ratio))

    try:
        arr: NDArray[np.float64] = np.asarray(embeddings, dtype=float)  # (m, d)
        if arr.ndim != 2:
            logger.error("[SELECT] Forme embeddings invalide: %s", arr.shape)
            return []
        target: NDArray[np.float64] = np.mean(arr, axis=0)  # (d,)
        sims: NDArray[np.float64] = cosine_similarity(target.reshape(1, -1), arr)[0]
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[SELECT] Erreur pré-calcul similarités : %s", exc)
        return []

    try:
        if use_mmr:
            central_idx = _mmr_select(target, arr, top_k=N, lambda_mult=mmr_lambda)
            # moments forts = plus éloignés du centroïde
            distances = np.linalg.norm(arr - target, axis=1)
            strong_idx = distances.argsort()[-2:]

            top_idx = list(set(central_idx + strong_idx.tolist()))
        else:
            top_idx = sims.argsort()[-N:][::-1].tolist()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[SELECT] Erreur MMR/fallback : %s", exc)
        top_idx = sims.argsort()[-N:][::-1].tolist()

    if return_scores:
        return [{"text": blocks[i], "score": float(sims[i]), "idx": i} for i in top_idx]
    return [blocks[i] for i in top_idx]
