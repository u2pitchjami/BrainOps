"""
# handlers/process/get_type.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from Levenshtein import ratio

from brainops.models.classification import ClassificationResult
from brainops.models.exceptions import BrainOpsError, ErrCode
from brainops.ollama.ollama_call import call_ollama_with_retry
from brainops.ollama.prompts import PROMPTS
from brainops.process_folders.folders import add_folder
from brainops.process_import.utils.divers import (
    prompt_name_and_model_selection,
)
from brainops.sql.categs.db_dictionary_categ import (
    generate_categ_dictionary,
    generate_optional_subcategories,
    get_categ_id_from_name,
    get_subcateg_from_categ,
)
from brainops.sql.folders.db_folder_utils import (
    get_folder_path_by_id,
    is_folder_exist,
)
from brainops.sql.get_linked.db_get_linked_folders_utils import (
    get_category_context_from_folder,
)
from brainops.utils.config import (
    MODEL_GET_TYPE,
    SIMILARITY_WARNINGS_LOG,
    Z_STORAGE_PATH,
)
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger

# ---------- Parse & nettoyage --------------------------------------------------


def parse_category_response(llama_proposition: str) -> str:
    """
    Extrait "Category/Subcategory" d'une réponse LLM.
    """
    match = re.search(r"([A-Za-z0-9_ ]+)/([A-Za-z0-9_ ]+)", llama_proposition or "")
    if match:
        return f"{match.group(1).strip()}/{match.group(2).strip()}"
    raise BrainOpsError(
        "[METADATA] ❌ Parse Categ KO",
        code=ErrCode.METADATA,
        ctx={"fonction": "parse_category_response", "llama_proposition": llama_proposition},
    )


@with_child_logger
def clean_note_type(parse_category: str, logger: LoggerProtocol | None = None) -> str:
    """
    Nettoyage: guillemets -> off, espaces -> _, interdits -> off, pas de '.' final.
    """
    logger = ensure_logger(logger, __name__)
    clean_str = parse_category.strip().replace('"', "").replace("'", "")
    clean_str = clean_str.replace("\n", "")
    clean_str = clean_str.replace(" ", "_")
    clean_str = re.sub(r'[\:*?"<>|]', "", clean_str)
    clean_str = re.sub(r"\.$", "", clean_str)
    return prep_and_similarity_test(clean_str, logger=logger)


# ---------- Similarité (inchangé) ---------------------------------------------


@with_child_logger
def find_similar_levenshtein(
    name: str,
    existing_names: str,
    threshold_low: float = 0.7,
    entity_type: str = "subcategory",
    logger: LoggerProtocol | None = None,
) -> list[tuple[str, float]]:
    """
    find_similar_levenshtein _summary_

    _extended_summary_

    Args:
        name (str): _description_
        existing_names (list[str]): _description_
        threshold_low (float, optional): _description_. Defaults to 0.7.
        entity_type (str, optional): _description_. Defaults to "subcategory".

    Returns:
        _type_: _description_
    """
    logger = ensure_logger(logger, __name__)
    logger.debug(
        f"[DEBUG] find_similar_levenshtein: name={name}, existing_names={existing_names}, entity_type={entity_type}"
    )
    similar: list[tuple[str, float]] = []
    try:
        for existing in existing_names:
            similarity = ratio(name, existing)
            logger.debug(f"[DEBUG] Similarity test '{name}' vs '{existing}' = {similarity:.2f}")
            if similarity >= threshold_low:
                similar.append((existing, similarity))
    except Exception as exc:
        raise BrainOpsError(
            "[METADATA] ❌ Erreur dans la recherche de similarité",
            code=ErrCode.METADATA,
            ctx={"fonction": "find_similar_levenshtein", "name": name},
        ) from exc
    return sorted(similar, key=lambda x: x[1], reverse=True)


@with_child_logger
def prep_and_similarity_test(note_type: str, logger: LoggerProtocol | None = None) -> str:
    logger = ensure_logger(logger, __name__)
    try:
        parts = [p.strip() for p in note_type.split("/", 1)]
        category_name = parts[0].lower()
        subcategory_name = parts[1].lower() if len(parts) == 2 and parts[1] else "unknow"
        if not category_name:
            raise BrainOpsError(
                "[METADATA] ❌ Impossible de parser la proposition Ollama",
                code=ErrCode.METADATA,
                ctx={"fonction": "prep_and_similarity_test", "note_type": note_type},
            )
        list_categ = generate_categ_dictionary(for_similar=True, logger=logger)
        logger.debug(f"list_categ: {list_categ}")
        real_category_name = check_and_handle_similarity(
            category_name, existing_names=list_categ, entity_type="category"
        )
        logger.debug(f"real_category_name: {real_category_name}")
        if subcategory_name is not None and real_category_name:
            cat_id = get_categ_id_from_name(name=real_category_name, logger=logger)
            logger.debug(f"cat_id: {cat_id}")
            if cat_id is None:
                real_subcategory_name = subcategory_name
            else:
                subcategs = get_subcateg_from_categ(categ_id=cat_id, logger=logger)
                if subcategs:
                    logger.debug(f"subcategs: {subcategs}")
                    check_subcategory_name = check_and_handle_similarity(
                        subcategory_name, existing_names=subcategs, entity_type="subcategory"
                    )
                else:
                    check_subcategory_name = subcategory_name
                logger.debug(f"check_subcategory_name: {check_subcategory_name}")
                if check_subcategory_name:
                    real_subcategory_name = check_subcategory_name
            if real_subcategory_name:
                return f"{real_category_name}/{real_subcategory_name}"
        raise BrainOpsError(
            "[METADATA] ❌ Recherche Categ/Sub KO",
            code=ErrCode.METADATA,
            ctx={"step": "prep_and_similarity_test", "note_type": note_type},
        )
    except Exception as exc:
        raise BrainOpsError(
            "[METADATA] ❌ Check similarités categ/subcateg KO",
            code=ErrCode.METADATA,
            ctx={
                "fonction": "_classify_with_llm",
                "real_category_name": real_category_name,
                "real_subcategory_name": real_subcategory_name,
            },
        ) from exc


@with_child_logger
def check_and_handle_similarity(
    name: str,
    existing_names: str,
    threshold_low: float = 0.7,
    entity_type: str = "subcategory",
    logger: LoggerProtocol | None = None,
) -> str | None:
    """
    check_and_handle_similarity _summary_

    _extended_summary_

    Args:
        name (str): _description_
        existing_names (list[str]): _description_
        threshold_low (float, optional): _description_. Defaults to 0.7.
        entity_type (str, optional): _description_. Defaults to "subcategory".

    Returns:
        Optional[str]: _description_
    """
    logger = ensure_logger(logger, __name__)
    logger.debug(
        f"[DEBUG] check_and_handle_similarity: name={name}, existing_names={existing_names}, entity_type={entity_type}"
    )
    threshold_high = 0.9
    similar = find_similar_levenshtein(name, existing_names, threshold_low, entity_type, logger=logger)
    logger.debug(f"[DEBUG] similar found: {similar}")
    if similar:
        closest, score = similar[0]
        if score >= threshold_high:
            logger.info(f"[INFO] {entity_type} '{name}' similaire à '{closest}' (score: {score:.2f}), on remplace.")
            # Fusion auto
            return closest
        if threshold_low <= score < threshold_high:
            logger.warning(f"[WARNING] {entity_type} '{name}' proche de '{closest}' (score: {score:.2f}), à vérifier.")
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = (
                f"[{current_time}] Doute sur {entity_type}: '{name}' proche de '{closest}' (score: {score:.2f})\n"
            )
            # On log dans le fichier prévu
            with open(SIMILARITY_WARNINGS_LOG, "a", encoding="utf-8") as log_file:
                log_file.write(log_message)
            return None
    return name


# ---------- Classification & déplacement --------------------------------------


@with_child_logger
def _classify_with_llm(note_id: int, content: str, *, logger: LoggerProtocol | None = None) -> str:
    """
    Construit le prompt et appelle Ollama.

    Retourne la chaîne brute (ex: "Dev/Python").
    """
    logger = ensure_logger(logger, __name__)
    try:
        # dictionnaires pour guider le LLM
        subcateg_dict = generate_optional_subcategories(logger=logger)
        logger.debug("[DEBUG] subcateg_dict _classify_with_llm : %s", subcateg_dict)
        categ_dict = generate_categ_dictionary(logger=logger)
        logger.debug("[DEBUG] categ_dict _classify_with_llm : %s", categ_dict)

        prompt_name, _ = prompt_name_and_model_selection(note_id, key="type", logger=logger)  # note_id pas requis ici
        logger.debug("[DEBUG] prompt_name _classify_with_llm : %s", prompt_name)
        model_ollama = MODEL_GET_TYPE
        prompt = PROMPTS[prompt_name].format(
            categ_dict=categ_dict,
            subcateg_dict=subcateg_dict,
            content=content[:1500],
        )
        logger.debug("[DEBUG] prompt _classify_with_llm : %s", prompt)
        return call_ollama_with_retry(prompt, model_ollama, logger=logger)
    except Exception as exc:
        raise BrainOpsError(
            "[METADATA] ❌ Construction prompt get_type KO",
            code=ErrCode.METADATA,
            ctx={"fonction": "_classify_with_llm", "note_id": note_id},
        ) from exc


@with_child_logger
def _resolve_destination(note_type: str, note_id: int, *, logger: LoggerProtocol | None = None) -> ClassificationResult:
    """
    À partir du note_type "Cat/Sub", calcule ids + dossier cible.
    """
    logger = ensure_logger(logger, __name__)
    try:
        subcat_id = None
        try:
            parts = [p.strip() for p in note_type.split("/", 1)]
            category_name = parts[0].lower().capitalize()
            subcategory_name = parts[1].lower().capitalize() if len(parts) == 2 and parts[1] else None
        except Exception as exc:  # pylint: disable=broad-except
            raise BrainOpsError(
                "[METADATA] ❌ Impossible de parser la proposition Ollama",
                code=ErrCode.METADATA,
                ctx={"fonction": "_resolve_destination", "note_id": note_id, "note_type": note_type},
            ) from exc

        categ_path = Path(Z_STORAGE_PATH) / category_name
        logger.debug(f"categ_path: {categ_path}")
        cat_folder_id = is_folder_exist(folderpath=str(categ_path), logger=logger)
        if not cat_folder_id:
            cat_folder_id = add_folder(folder_path=categ_path, logger=logger)
        logger.debug(f"cat_folder_id: {cat_folder_id}")
        categ_path = Path(get_folder_path_by_id(folder_id=cat_folder_id, logger=logger))
        if subcategory_name is not None:
            subcateg_path = categ_path / subcategory_name
            logger.debug(f"subcateg_path: {subcateg_path}")
            sub_folder_id = is_folder_exist(folderpath=str(subcateg_path), logger=logger)
            if not sub_folder_id:
                sub_folder_id = add_folder(folder_path=subcateg_path, logger=logger)
            logger.debug(f"sub_folder_id: {sub_folder_id}")
            def_path = get_folder_path_by_id(sub_folder_id, logger=logger)
            logger.debug(f"def_path: {def_path}")
            classification = get_category_context_from_folder(def_path, logger=logger)
            logger.debug(f"classification: {classification}")
        else:
            def_path = get_folder_path_by_id(cat_folder_id, logger=logger)
            classification = get_category_context_from_folder(def_path, logger=logger)

    except Exception as exc:
        raise BrainOpsError(
            "[METADATA] ❌ Impossible d'indentifier une localisation à partir de la proposition Ollama",
            code=ErrCode.METADATA,
            ctx={"fonction": "_resolve_destination", "note_id": note_id, "note_type": note_type},
        ) from exc
    return ClassificationResult(
        category_name=classification.category_name or category_name,
        category_id=classification.category_id,
        subcategory_name=classification.subcategory_name or subcategory_name,
        subcategory_id=classification.subcategory_id or subcat_id,
        folder_id=sub_folder_id or cat_folder_id,
        dest_folder=def_path,
        status=classification.status,
    )
