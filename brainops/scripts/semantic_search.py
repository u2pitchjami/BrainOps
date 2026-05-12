# #!/usr/bin/env python3
# """
# # scripts/semantic_search.py
# """

# from __future__ import annotations

# import argparse
# import json
# from pathlib import Path
# from typing import TypedDict

# import numpy as np
# from numpy.typing import ArrayLike, NDArray

# from brainops.ollama.ollama_call import get_embedding
# from brainops.sql.temp_blocs.db_embeddings_temp_blocs import get_blocks_and_embeddings_by_note
# from brainops.utils.logger import LoggerProtocol, get_logger

# logger: LoggerProtocol = get_logger("semantic_search")


# class SearchHit(TypedDict):
#     text: str
#     score: float


# def _as_np2d(vectors: ArrayLike) -> NDArray[np.float32]:
#     """
#     Convertit un vecteur 1D ou une matrice 2D en np.float32 2D :

#     - (1, d) si l'entrée est 1D
#     - (n, d) si l'entrée est 2D
#     """
#     arr = np.asarray(vectors, dtype=np.float32)
#     if arr.ndim == 1:
#         arr = arr.reshape(1, -1)
#     if arr.ndim != 2:
#         raise ValueError(f"Expected 1D or 2D input, got ndim={arr.ndim}")
#     return arr


# def _cosine_sim_row_to_matrix(q: NDArray[np.float32], M: NDArray[np.float32]) -> NDArray[np.float32]:
#     """
#     Cosine similarity entre un seul vecteur (1, d) et une matrice (n, d).

#     Retourne un tableau (1, n).
#     """
#     eps = np.finfo(np.float32).eps
#     qn = q / (np.linalg.norm(q, axis=1, keepdims=True) + eps)
#     Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + eps)
#     return qn @ Mn.T


# def search_blocks_by_semantic(
#     query_text: str,
#     *,
#     note_id: int | None,
#     top_n: int = 5,
#     embed_model: str = "nomic-embed-text:latest",
# ) -> list[SearchHit]:
#     """
#     Recherche sémantique des blocs d'une note via embeddings + cosine similarity.

#     - note_id: identifiant de la note (obligatoire pour l’instant)
#     - embed_model: modèle d'embedding ollama (par défaut: nomic-embed-text:latest)
#     """
#     if not note_id:
#         logger.error("Recherche globale non encore implémentée (note_id requis).")
#         return []

#     blocks, embeddings = get_blocks_and_embeddings_by_note(note_id, logger=logger)
#     if not blocks or not embeddings:
#         logger.info("Aucun bloc ou embedding trouvé pour note_id=%s.", note_id)
#         return []

#     query_vec = get_embedding(query_text, embed_model, logger=logger)
#     if query_vec is None:
#         logger.error("Embedding de la requête introuvable (None).")
#         return []

#     try:
#         emb_mat = _as_np2d(embeddings)  # (N, D)
#         q = _as_np2d(query_vec)  # (1, D)
#         if emb_mat.size == 0 or q.size == 0:
#             logger.info("Embeddings vides (size=0) pour note_id=%s.", note_id)
#             return []
#         if emb_mat.shape[1] != q.shape[1]:
#             logger.error(
#                 "Dimension embedding incohérente: blocs=%s vs query=%s",
#                 emb_mat.shape,
#                 q.shape,
#             )
#             return []
#         sims = _cosine_sim_row_to_matrix(q, emb_mat).ravel()  # (N,)
#         k = min(max(int(top_n), 0), sims.shape[0])
#         if k == 0:
#             return []
#         top_idx = np.argpartition(sims, -k)[-k:]  # O(N) sélection
#         # tri final décroissant
#         top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]
#         return [{"text": blocks[i], "score": float(sims[i])} for i in top_idx]
#     except Exception as exc:
#         logger.exception("Erreur similarity: %s", exc)
#         return []


# def main() -> None:
#     """
#     Main _summary_

#     _extended_summary_
#     """
#     parser = argparse.ArgumentParser(description="Recherche sémantique IA locale sur Obsidian")
#     parser.add_argument("--query", required=True, help="Texte ou question à chercher")
#     parser.add_argument("--note_id", type=int, required=True, help="ID de la note cible")
#     parser.add_argument("--top", type=int, default=5, help="Nombre de blocs à retourner")
#     parser.add_argument(
#         "--embed-model",
#         type=str,
#         default="nomic-embed-text:latest",
#         help="Modèle d'embedding Ollama (default: nomic-embed-text:latest)",
#     )
#     parser.add_argument("--out", type=str, help="Fichier de sortie (.md ou .json)")
#     args = parser.parse_args()

#     results = search_blocks_by_semantic(
#         args.query,
#         note_id=args.note_id,
#         top_n=args.top,
#         embed_model=args.embed_model,
#     )

#     if args.out:
#         out = Path(args.out)
#         out.parent.mkdir(parents=True, exist_ok=True)
#         if out.suffix.lower() == ".json":
#             out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
#         else:
#             lines = [f"## Bloc {i + 1} (score {r['score']:.2f})\n{r['text']}\n\n" for i, r in enumerate(results)]
#             out.write_text("".join(lines), encoding="utf-8")
#         logger.info("Résultats écrits dans : %s", out)
#     else:
#         # sortie CLI lisible
#         for r in results:
#             print(f"\n[Score {r['score']:.2f}]")
#             print(r["text"])


# if __name__ == "__main__":
#     main()
