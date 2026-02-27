"""
# handlers/process/synthesis.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from brainops.header.headers import make_properties
from brainops.models.classification import ClassificationResult
from brainops.models.metadata import NoteMetadata
from brainops.process_import.join.join_header_body import join_header_body
from brainops.process_import.synthese.add_or_update import new_synthesis, update_synthesis
from brainops.process_import.synthese.embeddings import make_embeddings_synthesis
from brainops.process_import.synthese.synthesis_utils import (
    make_glossary,
    make_questions,
    make_syntheses,
)
from brainops.process_import.utils.divers import make_relative_link
from brainops.utils.logger import LoggerProtocol, ensure_logger, with_child_logger


@with_child_logger
def process_import_syntheses(
    content: str,
    note_id: int,
    archive_path: Path,
    synthesis_path: Path,
    meta_final: NoteMetadata,
    classification: ClassificationResult,
    *,
    media_id: int | None = None,
    regen: bool = False,
    remake_header: bool = False,
    logger: LoggerProtocol | None = None,
) -> bool:
    """
    Orchestrateur de la génération de synthèse :

    - si pas de parent → copie en 'archive' et embeddings sur la note
    - sinon → embeddings sur l'archive liée
    - construit glossaire, questions, traduction FR si besoin
    - écrit le fichier final et met à jour le YAML/DB (status='synthesis')
    """
    logger = ensure_logger(logger, __name__)
    logger.info("[SYNTH] ▶️ Génération de la synthèse pour : (id=%s)", note_id)
    logger.debug("[DEBUG] +++ ▶️ SYNTHESE pour %s", note_id)
    try:
        logger.info("[SYNTH] Démarage Embeddings pour : (id=%s)", note_id)

        final_response = make_embeddings_synthesis(
            note_id,
            content=content,
            source_note=meta_final.doc_type,
            max_chars=3800,
            max_tokens=500,
            logger=logger,
        )

        if not final_response:
            logger.error("[ERROR] ❌ final_response None: abandon synthèse.")
            return False
        logger.info("[SYNTH] 👌 Embeddings OK : (id=%s)", note_id)

        original_path = make_relative_link(archive_path, synthesis_path, logger=logger)
        logger.debug("[DEBUG] original_path (relative link) : %s", original_path)
        if not original_path:
            logger.error("[ERROR] ❌ Lien synthèse - archive introuvable")
        logger.info("[SYNTH] 👌 Lien Synthèse <--> Archive OK : (id=%s)", note_id)

        logger.debug("[DEBUG] Génération du glossaire…")
        glossary = make_glossary(content, note_id, logger=logger)
        if not glossary:
            logger.error("[ERROR] ❌ Glossaire KO")
        logger.info("[SYNTH] 👌 Glossaire OK : (id=%s)", note_id)

        logger.debug("[DEBUG] Génération des questions…")
        questions = make_questions(
            note_id=note_id,
            content=content,
            logger=logger,
        )
        if not questions:
            logger.error("[ERROR] ❌ Génération des questions.")
        logger.info("[SYNTH] 👌 Questions OK : (id=%s)", note_id)

        translate_synth: str | None = None
        # note_lang = get_note_lang(note_id, logger=logger)
        # if note_lang and note_lang != "fr":
        #     logger.debug("[DEBUG] Traduction synthèse (lang=%s → fr)…", note_lang)
        #     translate_synth = make_translate(final_response, note_id, logger=logger)

        logger.debug("[DEBUG] Assemblage du corps de la synthèse…")
        final_synth_body_content = make_syntheses(
            note_id=note_id,
            original_path=str(original_path),
            translate_synth=translate_synth,
            glossary=glossary,
            questions=questions,
            content_lines=final_response,
            logger=logger,
        )
        logger.debug("[DEBUG] Maj propriétés (status='synthesis')…")
        if not remake_header:
            meta_synth_final = NoteMetadata.merge(
                NoteMetadata(  # priorité aux nouvelles infos
                    tags=meta_final.tags,
                    summary=meta_final.summary,
                    status="synthesis",
                    category=classification.category_name,
                    subcategory=classification.subcategory_name or "",
                    last_modified=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    doc_type=meta_final.doc_type,
                ),
                meta_final,  # puis l’existant
            )
        else:
            meta_synth_final = make_properties(
                content=final_response,
                meta_yaml=meta_final,
                classification=classification,
                note_id=note_id,
                status="synthesis",
                logger=logger,
            )

        if not regen:
            join_synthesis = new_synthesis(
                final_synth_body_content=final_synth_body_content,
                note_id=note_id,
                media_id=media_id,
                synthesis_path=synthesis_path,
                meta_synth_final=meta_synth_final,
                classification=classification,
                logger=logger,
            )
        else:
            join_synthesis = update_synthesis(
                final_synth_body_content=final_synth_body_content,
                note_id=note_id,
                synthesis_path=synthesis_path,
                meta_synth_final=meta_synth_final,
                classification=classification,
                logger=logger,
            )
        if not join_synthesis:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement en base (id=%s)",
                note_id,
            )
            return False

        synthesis_def = join_header_body(
            body=final_synth_body_content,
            meta_yaml=meta_synth_final,
            filepath=synthesis_path,
            write_file=True,
            logger=logger,
        )
        if not synthesis_def:
            logger.error(
                "[ERREUR] 🚨 Problème lors de l'enregistrement de l'archive (id=%s)",
                note_id,
            )
            return False

        logger.debug("[DEBUG] === ⏹️ FIN SYNTHESE pour %s", note_id)
        logger.info("[INFO] ✅ Synthèse terminée pour (id=%s)", note_id)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[ERREUR] Impossible de traiter %s : %s", note_id, exc)
        return False
