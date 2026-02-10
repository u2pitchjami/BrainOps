"""
# process/embeddings_utils.py
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.ollama.ollama_utils import large_or_standard_note
from brainops.process_import.synthese.embeddings_gpt import build_summary_prompt_gpt
from brainops.process_import.synthese.embeddings_normal import build_summary_prompt
from brainops.process_import.synthese.embeddings_utils import select_top_blocks_by_mode
from brainops.utils.config import MODEL_EMBEDDINGS, MODEL_FR
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def make_embeddings_synthesis(
    note_id: int,
    content: str,
    *,
    source: str = "normal",
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
            source,
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
            word_limit=100,
            note_id=note_id,
            persist_blocks=True,
            send_to_model=True,
            logger=logger,
        )

        # 2) top blocs (avec score pour debug)
        top_blocks = select_top_blocks_by_mode(content=content, note_id=note_id, mode=mode, logger=logger)
        logger.debug("[DEBUG] top_blocks: %s", top_blocks)
        # 3) synthèse finale
        if source == "gpt":
            prompt = build_summary_prompt_gpt(top_blocks, structure="brainops", require_json=False)
            logger.debug("[DEBUG] prompt: %s", prompt)
        else:
            prompt = build_summary_prompt(blocks=top_blocks)

        final_response = call_ollama_with_retry(prompt, model_ollama=MODEL_FR, logger=logger)
        return final_response
    except Exception as exc:
        raise BrainOpsError("Emvbeddings KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
