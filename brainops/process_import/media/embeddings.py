"""
# process/embeddings_utils.py
"""

from __future__ import annotations

from brainops.embeddings.ollama_provider import OllamaEmbeddingProvider
from brainops.embeddings.repositories.temp_blocks_repository import TempBlocksEmbeddingRepository
from brainops.embeddings.transcript_indexer import process_note_embeddings
from brainops.io.utils import count_words
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.models.note_context import NoteContext
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.process_import.media.embeddings_normal import build_summary_prompt
from brainops.process_import.media.embeddings_utils import select_top_blocks_by_mode
from brainops.process_import.split.split_main import SplitMethod
from brainops.process_import.split.split_utils import count_tokens
from brainops.sql.temp_blocs.db_delete_temp_blocs import delete_blocs_by_path_and_source
from brainops.utils.config import MODEL_EMBEDDINGS, MODEL_FR
from brainops.utils.logger import LoggerProtocol, ensure_logger


def make_embeddings_synthesis(
    content: str,
    ctx: NoteContext,
    *,
    max_chars: int = 3800,
    max_tokens: int = 1500,
    mode: str = "ajust",
    split_method: SplitMethod = "auto",
    logger: LoggerProtocol | None = None,
) -> str | None:
    """
    1) Génère/persiste des embeddings via 'large_or_standard_note' (mode embeddings) 2) Sélectionne les meilleurs blocs
    3) Construit le prompt et appelle le modèle de synthèse Retourne le texte de synthèse ou None en cas d'échec.
    """
    logger = ensure_logger(logger, __name__)
    try:
        note_id = ctx.note_db.id

        if note_id is None:
            raise ValueError("La note doit être enregistrée en base avant la synthèse.")

        delete_blocs_by_path_and_source(
            note_id=note_id,
            source="embeddings",
            logger=logger,
        )
        # 1) création des embeddings + stockage des blocs (process_large_note côté projet)
        process_note_embeddings(
            ctx=ctx,
            model_name=MODEL_EMBEDDINGS,
            provider=OllamaEmbeddingProvider(),
            repository=TempBlocksEmbeddingRepository(),
            resume_if_possible=True,
            split_method="auto",
            max_token=1500,
            max_chars=3800,
            logger=logger,
        )

        # _ = large_or_standard_note(
        #     content=content,
        #     source="embeddings",
        #     process_mode="large_note",
        #     prompt_name="embeddings",
        #     model_ollama=MODEL_EMBEDDINGS,
        #     write_file=False,
        #     split_method=split_method,
        #     max_chars=max_chars,
        #     max_tokens=max_tokens,
        #     note_id=note_id,
        #     persist_blocks=True,
        #     send_to_model=True,
        #     logger=logger,
        # )

        word_count = count_words(
            content=content,
            logger=logger,
        )

        selection_mode = "quick" if word_count < 300 else ctx.analysis.selection_mode

        top_blocks = select_top_blocks_by_mode(
            content=content,
            note_id=note_id,
            mode_def=selection_mode,
            logger=logger,
        )

        logger.debug(
            "[SYNTHESIS] note_id=%s profile=%s selection_mode=%s block_count=%s",
            note_id,
            ctx.analysis.profile,
            selection_mode,
            len(top_blocks),
        )

        prompt = build_summary_prompt(
            blocks=top_blocks,
            ctx=ctx,
        )
        logger.debug("[SYNTHESIS] prompt=%s", prompt)

        synthesis_token_count = count_tokens(prompt)

        logger.debug(
            "[SYNTHESIS] note_id=%s prompt_tokens=%s",
            note_id,
            synthesis_token_count,
        )

        # 3) synthèse finale

        final_response = call_ollama_with_retry(prompt, model_ollama=MODEL_FR, logger=logger)
        return final_response
    except Exception as exc:
        raise BrainOpsError("Emvbeddings KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
