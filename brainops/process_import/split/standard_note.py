"""
process_import.utils.standard_note.py.
"""

from __future__ import annotations

from brainops.embeddings.transcript_indexer import compute_text_hash, normalize_embedding_text
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.ollama.prompts import PROMPTS
from brainops.sql.temp_blocs.db_temp_blocs import (
    get_existing_bloc,
    insert_bloc,
    update_bloc_response,
)
from brainops.utils.files import maybe_clean
from brainops.utils.logger import LoggerProtocol, ensure_logger
from brainops.utils.normalization import clean_fake_code_blocks


def process_standard_note(
    note_id: int,
    model_ollama: str,
    content: str,
    prompt_name: str = "import",
    source: str = "import",
    write_file: bool = True,
    resume_if_possible: bool = True,
    *,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Traite une note entière (bloc unique) et, si write_file=True.

    Retourne la réponse brute (texte) si write_file=False, sinon None.
    """
    logger = ensure_logger(logger, __name__)

    # 2) Prompt
    prompt_tpl = PROMPTS.get(prompt_name)
    if not prompt_tpl:
        logger.error("Prompt '%s' introuvable dans PROMPTS.", prompt_name)
        raise BrainOpsError("Prompt introuvable", code=ErrCode.OLLAMA, ctx={"note_id": note_id})
    prompt = prompt_tpl.format(content=content)

    normalized_text = normalize_embedding_text(content)

    block_index = 0
    split_method = "none"
    word_limit = 0

    # 3) Resume si déjà traité
    existing = get_existing_bloc(
        note_id=note_id,
        block_index=block_index,
        prompt=prompt_name,
        model=model_ollama,
        split_method=split_method,
        word_limit=word_limit,
        source=source,
        content_hash=compute_text_hash(normalized_text),
        logger=logger,
    )
    if existing and existing.status == "processed" and resume_if_possible and existing.response:
        logger.info("[SKIP] Note déjà traitée : %s", note_id)
        return existing.response.strip()

    # 4) Insert + appel LLM
    block_id = insert_bloc(
        note_id=note_id,
        block_index=block_index,
        content=content,
        prompt=prompt_name,
        model=model_ollama,
        split_method=split_method,
        word_limit=word_limit,
        source=source,
        content_hash=compute_text_hash(normalized_text),
        logger=logger,
    )

    response = call_ollama_with_retry(prompt, model_ollama, logger=logger) or ""
    response_clean = clean_fake_code_blocks(maybe_clean(response)).strip()

    update_bloc_response(
        block_id=block_id,
        response=response or "",
        status="processed",
        logger=logger,
    )

    # 6) Retour "brut" compatible
    return response_clean
