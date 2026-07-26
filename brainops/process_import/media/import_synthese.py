"""
# handlers/process/synthesis.py
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from brainops.header.headers import make_properties
from brainops.models.metadata import NoteMetadata
from brainops.models.note_context import NoteContext
from brainops.process_import.join.join_header_body import join_header_body
from brainops.process_import.media.add_or_update import update_synthesis
from brainops.process_import.media.embeddings import make_embeddings_synthesis
from brainops.process_import.media.synthesis_utils import (
    make_glossary,
    make_questions,
    make_syntheses,
    make_translate,
)
from brainops.sql.get_linked.db_get_linked_notes_utils import get_note_lang
from brainops.utils.files import clean_content
from brainops.utils.logger import LoggerProtocol, ensure_logger


def process_import_syntheses(
    content: str,
    note_id: int,
    synthesis_path: Path,
    meta_final: NoteMetadata,
    ctx: NoteContext,
    *,
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
            ctx=ctx,
            content=content,
            max_chars=3800,
            max_tokens=500,
            logger=logger,
        )

        if not final_response:
            logger.error("[ERROR] ❌ final_response None: abandon synthèse.")
            return False
        logger.info("[SYNTH] 👌 Embeddings OK : (id=%s)", note_id)

        logger.debug("[DEBUG] Génération du glossaire…")
        glossary = make_glossary(content, note_id, logger=logger)
        if not glossary:
            logger.error("[ERROR] ❌ Glossaire KO")
        logger.info("[SYNTH] 👌 Glossaire OK : (id=%s)", note_id)

        cont_synth = clean_content(final_response)
        logger.debug("[DEBUG] Génération des questions…")
        questions = make_questions(
            note_id=note_id,
            content=cont_synth,
            logger=logger,
        )
        if not questions:
            logger.error("[ERROR] ❌ Génération des questions.")
        logger.info("[SYNTH] 👌 Questions OK : (id=%s)", note_id)

        translate_synth: str | None = None
        note_lang = get_note_lang(note_id, logger=logger)
        if note_lang and note_lang != "fr":
            logger.debug("[DEBUG] Traduction synthèse (lang=%s → fr)…", note_lang)
            translate_synth = make_translate(final_response, note_id, logger=logger)

        logger.debug("[DEBUG] Assemblage du corps de la synthèse…")
        final_synth_body_content = make_syntheses(
            note_id=note_id,
            content=content,
            original_path=str(synthesis_path),
            translate_synth=translate_synth,
            glossary=glossary,
            questions=questions,
            synth_lines=final_response,
            logger=logger,
        )
        logger.debug("[DEBUG] Maj propriétés (status='synthesis')…")
        if not remake_header:
            meta_synth_final = NoteMetadata.merge(
                NoteMetadata(  # priorité aux nouvelles infos
                    status="synthesis",
                    last_modified=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    doc_type=meta_final.doc_type,
                    analysis_profile=ctx.note_metadata.analysis_profile if ctx.note_metadata else "generic",
                ),
                meta_final,  # puis l’existant
            )
        else:
            meta_synth_final = make_properties(
                content=final_response,
                meta_yaml=meta_final,
                note_id=note_id,
                status="synthesis",
                logger=logger,
            )

        join_synthesis = update_synthesis(
            final_synth_body_content=final_synth_body_content,
            note_id=note_id,
            synthesis_path=synthesis_path,
            meta_synth_final=meta_synth_final,
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
