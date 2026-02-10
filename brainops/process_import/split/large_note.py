"""
process_import.utils.large_note.
"""

from __future__ import annotations

import json

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.ollama.ollama_call import OllamaError, call_ollama_with_retry
from brainops.ollama.prompts import PROMPTS
from brainops.process_import.split.split_main import smart_split_for_embeddings, split_large_note_by_titles_and_words
from brainops.process_import.split.split_qa_paragraphs import split_qa_paragraphs
from brainops.process_import.split.split_utils import (
    ensure_titles_in_blocks,
    split_large_note,
    split_large_note_by_titles,
)
from brainops.process_import.split.split_windows_by_paragraphs import split_windows_by_paragraphs
from brainops.sql.temp_blocs.db_error_temp_blocs import mark_bloc_as_error
from brainops.sql.temp_blocs.db_temp_blocs import (
    get_existing_bloc,
    insert_bloc,
    update_bloc_response,
)
from brainops.utils.config import MODEL_LARGE_NOTE
from brainops.utils.files import maybe_clean
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger
from brainops.utils.normalization import clean_fake_code_blocks


@with_child_logger
def process_large_note(
    note_id: int,
    content: str,
    entry_type: str | None = None,
    word_limit: int = 100,
    split_method: str = "auto",
    write_file: bool = True,
    send_to_model: bool = True,
    model_name: str | None = None,
    persist_blocks: bool = True,
    resume_if_possible: bool = True,
    source: str = "normal",
    *,
    logger: LoggerProtocol | None = None,
) -> str:
    logger = ensure_logger(logger, __name__)

    model_ollama = model_name or MODEL_LARGE_NOTE

    if not entry_type:
        logger.error("[ERROR] Aucun 'entry_type' (clé PROMPTS) ni 'custom_prompts' fournis.")
        raise BrainOpsError("large_note KO", code=ErrCode.UNEXPECTED, ctx={"note_id": note_id})

    try:
        # --- split
        if split_method == "auto":
            blocks = smart_split_for_embeddings(content)
        elif split_method == "titles_and_words":
            blocks = split_large_note_by_titles_and_words(content)
        elif split_method == "titles":
            blocks = split_large_note_by_titles(content)
        elif split_method == "words":
            blocks = split_large_note(content, max_words=word_limit)
        elif split_method == "qa_paragraphs":
            blocks = split_qa_paragraphs(text=content, logger=logger)
        elif split_method == "split_windows_by_paragraphs":
            blocks = split_windows_by_paragraphs(text=content)
        else:
            logger.error("[ERROR] Méthode de split inconnue : %s", split_method)
            raise BrainOpsError("Méthode de split inconnue", code=ErrCode.UNEXPECTED, ctx={"note_id": note_id})

        logger.info("[INFO] Note découpée en %d blocs avec la méthode : %s", len(blocks), split_method)
        processed_blocks: list[str] = []

        for i, block in enumerate(blocks):
            logger.debug("[DEBUG] Bloc %d/%d", i + 1, len(blocks))
            block_index = i

            # Vérifie si déjà traité (si persistance active)
            if persist_blocks:
                try:
                    row = get_existing_bloc(
                        note_id=note_id,
                        block_index=block_index,
                        prompt=entry_type or "",  # ok si custom_prompts
                        model=model_ollama,
                        split_method=split_method,
                        word_limit=word_limit,
                        source=source,
                        logger=logger,
                    )
                    if row:
                        response_pb, status = row
                        logger.debug("[DEBUG] Bloc row %s", row)
                        if status == "processed" and resume_if_possible:
                            logger.debug("[DEBUG] Bloc %d déjà traité, skip", i)
                            if isinstance(response_pb, list):
                                response_pb = "\n".join(map(str, response_pb))
                            elif not isinstance(response_pb, str):
                                response_pb = str(response_pb)
                            processed_blocks.append(response_pb.strip())
                            continue
                    else:
                        insert_bloc(
                            note_id=note_id,
                            block_index=block_index,
                            content=block,
                            prompt=entry_type or "",
                            model=model_ollama,
                            split_method=split_method,
                            word_limit=word_limit,
                            source=source,
                            logger=logger,
                        )
                except Exception as exc:
                    raise BrainOpsError("Insertion bloc KO", code=ErrCode.DB, ctx={"note_id": note_id}) from exc

            # Traitement du bloc
            response: str | list[str] | None = block
            if send_to_model:
                # Sélection du prompt
                prompt_tpl = PROMPTS.get(entry_type or "")
                if not prompt_tpl:
                    logger.error("[ERROR] Prompt '%s' introuvable dans PROMPTS.", entry_type)
                    prompt = block  # fallback minimal
                else:
                    prompt = prompt_tpl.format(content=block)

            try:
                response = call_ollama_with_retry(prompt, model_ollama, logger=logger)
            except OllamaError:
                logger.error("[ERROR] Échec du bloc %d, saut…", i + 1)
                if persist_blocks:
                    mark_bloc_as_error(note_id, block_index, logger=logger)
                continue

            # Normalisation de la réponse
            if source == "embeddings":
                # response devrait être une list[float] renvoyée par get_embedding()
                if isinstance(response, list):
                    response = json.dumps(response)  # OK: on stocke un JSON array
                elif isinstance(response, str):
                    s = response.strip()
                    if s.startswith("[") and s.endswith("]"):
                        # déjà un JSON array → on le garde tel quel
                        response = s
                    else:
                        # on essaie de normaliser proprement
                        try:
                            parsed = json.loads(s)
                            if isinstance(parsed, list):
                                response = json.dumps(parsed)
                            else:
                                response = "null"
                        except Exception:
                            response = "null"
            else:
                if isinstance(response, list):
                    response = "\n".join(map(str, response))
                elif not isinstance(response, str):
                    response = str(response)

            if persist_blocks:
                update_bloc_response(
                    note_id=note_id,
                    block_index=block_index,
                    response=response or "",
                    source=source,
                    status="processed",
                    logger=logger,
                )

            processed_blocks.append((response or "").strip())

        # Titre de secours par bloc si manquant
        final_blocks = ensure_titles_in_blocks(processed_blocks)

        # ✅ Correction: on assemble en texte puis nettoyage
        blocks_text = "\n\n".join(final_blocks)
        logger.debug("Large Note -> block_text : %s", blocks_text[:300])
        final_body_content: str = clean_fake_code_blocks(maybe_clean(blocks_text))
        logger.debug("Large Note -> final_body_content : %s", final_body_content[:300])

        return final_body_content
    except Exception as exc:
        logger.exception("[ERREUR] Traitement de %s échoué : %s", note_id, exc)
        raise BrainOpsError("large note KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
