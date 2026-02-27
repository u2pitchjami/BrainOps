"""
# process/embeddings_utils.py
"""

from __future__ import annotations

from brainops.io.utils import count_words
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.ollama.ollama_utils import large_or_standard_note
from brainops.process_import.split.split_utils import count_tokens
from brainops.process_import.synthese.embeddings_normal import build_summary_prompt
from brainops.process_import.synthese.embeddings_podcast import build_podcast_summary_prompt
from brainops.process_import.synthese.embeddings_utils import select_top_blocks_by_mode
from brainops.utils.config import MODEL_EMBEDDINGS, MODEL_FR
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def make_embeddings_synthesis(
    note_id: int,
    content: str,
    source_note: str,
    *,
    max_chars: int = 3800,
    max_tokens: int = 1500,
    mode: str = "ajust",
    split_method: str = "auto",
    logger: LoggerProtocol | None = None,
) -> str | None:
    """
    1) Génère/persiste des embeddings via 'large_or_standard_note' (mode embeddings) 2) Sélectionne les meilleurs blocs
    3) Construit le prompt et appelle le modèle de synthèse Retourne le texte de synthèse ou None en cas d'échec.
    """
    logger = ensure_logger(logger, __name__)
    try:
        logger.debug(
            "[DEBUG] make_embeddings_synthesis id: %s source:%s mode:%s split_method:%s",
            note_id,
            source_note,
            mode,
            split_method,
        )
        # 1) création des embeddings + stockage des blocs (process_large_note côté projet)
        _ = large_or_standard_note(
            content=content,
            source="embeddings",
            process_mode="large_note",
            prompt_name="embeddings",
            model_ollama=MODEL_EMBEDDINGS,
            write_file=False,
            split_method=split_method,
            max_chars=max_chars,
            max_tokens=max_tokens,
            note_id=note_id,
            persist_blocks=True,
            send_to_model=True,
            logger=logger,
        )

        # 2) top blocs (avec score pour debug)

        # 3) synthèse finale
        if source_note == "podcast":
            top_blocks = select_top_blocks_by_mode(content=content, note_id=note_id, mode_def="podcast", logger=logger)
            logger.debug("[DEBUG] top_blocks: %s", top_blocks)
            prompt = build_podcast_summary_prompt(top_blocks)
            logger.debug("[DEBUG] prompt: %s", prompt)
        else:
            nb_words = count_words(content=content, logger=logger)
            if nb_words < 300:
                mode_def = "quick"
            else:
                mode_def = "standard"
            top_blocks = select_top_blocks_by_mode(content=content, note_id=note_id, mode_def=mode_def, logger=logger)
            prompt = build_summary_prompt(blocks=top_blocks)

        synthesis_nb_tokens = count_tokens(prompt)
        logger.debug("[DEBUG] synthesis_nb_tokens: %s", synthesis_nb_tokens)
        final_response = call_ollama_with_retry(prompt, model_ollama=MODEL_FR, logger=logger)
        return final_response
    except Exception as exc:
        raise BrainOpsError("Emvbeddings KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
