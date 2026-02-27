"""
# ollama/ollama_utils.py
"""

from __future__ import annotations

from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.process_import.split.large_note import process_large_note
from brainops.process_import.split.standard_note import process_standard_note
from brainops.process_import.utils.divers import prompt_name_and_model_selection
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def large_or_standard_note(
    note_id: int,
    content: str,
    prompt_key: str | None = None,
    model_ollama: str | None = None,
    max_chars: int = 3800,
    max_tokens: int = 1500,
    split_method: str = "auto",
    write_file: bool = True,
    send_to_model: bool = True,
    custom_prompts: dict[str, str] | None = None,
    persist_blocks: bool = True,
    resume_if_possible: bool = True,
    source: str = "normal",
    process_mode: str = "large_note",  # "large_note" | "standard_note"
    prompt_name: str | None = None,
    *,
    logger: LoggerProtocol | None = None,
) -> str:
    """
    Routeur entre 'process_large_note' et 'process_standard_note'.

    Retourne toujours une chaîne (éventuellement vide) pour compat ascendante.
    """
    logger = ensure_logger(logger, __name__)
    try:
        logger.debug("[DEBUG] large_or_standard_note model_ollama (in) : %s", model_ollama)

        # Déterminer prompt_name + model si non fournis explicitement
        if not prompt_name:
            if prompt_key:
                pn, mdl = prompt_name_and_model_selection(note_id, key=prompt_key, logger=logger)
                prompt_name = pn
                model_ollama = model_ollama or mdl
                logger.debug(
                    "[DEBUG] large_or_standard_note resolved def_model_ollama : %s",
                    model_ollama,
                )
            else:
                logger.error("[ERREUR] Aucun prompt_name/prompt_key fourni. Abandon.")
                raise BrainOpsError(
                    "large_or_standard_note : Aucun prompt_name/prompt_key fourni. Abandon",
                    code=ErrCode.OLLAMA,
                    ctx={"note_id": note_id},
                )

        if process_mode == "large_note":
            return (
                process_large_note(
                    note_id=note_id,
                    content=content,
                    entry_type=prompt_name,
                    max_chars=max_chars,
                    max_tokens=max_tokens,
                    split_method=split_method,
                    write_file=write_file,
                    send_to_model=send_to_model,
                    model_name=model_ollama,
                    persist_blocks=persist_blocks,
                    resume_if_possible=resume_if_possible,
                    source=source,
                    logger=logger,
                )
                or ""
            )

        if process_mode == "standard_note":
            if not model_ollama:
                raise BrainOpsError(
                    "large_or_standard_note : Aucun prompt_name/prompt_key fourni. Abandon",
                    code=ErrCode.OLLAMA,
                    ctx={"note_id": note_id},
                )

            logger.debug(
                "[DEBUG] large_or_standard_note → standard_note (model=%s)",
                model_ollama,
            )
            return (
                process_standard_note(
                    note_id=note_id,
                    content=content or "",
                    model_ollama=model_ollama,
                    prompt_name=prompt_name,
                    source=source,
                    write_file=write_file,
                    resume_if_possible=resume_if_possible,
                    logger=logger,
                )
                or ""
            )

        logger.error("[ERREUR] Mode de traitement inconnu : %s", process_mode)
        return ""
    except Exception as exc:
        raise BrainOpsError("large_or_standard_note KO", code=ErrCode.OLLAMA, ctx={"note_id": note_id}) from exc
