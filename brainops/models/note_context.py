from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brainops.header.header_utils import hash_source
from brainops.io.note_reader import read_note_full
from brainops.io.utils import count_words
from brainops.models.classification import ClassificationResult
from brainops.models.metadata import NoteMetadata
from brainops.models.note import Note
from brainops.process_import.utils.divers import hash_content, lang_detect
from brainops.sql.get_linked.db_get_linked_folders_utils import get_category_context_from_folder
from brainops.sql.notes.db_update_notes import _ALLOWED_COLUMNS
from brainops.utils.logger import LoggerProtocol, ensure_logger
from brainops.utils.normalization import sanitize_created, sanitize_yaml_title


@dataclass
class NoteContext:
    note_db: Note
    file_path: str
    src_path: str | None
    base_fp: str | None = None
    note_classification: ClassificationResult | None = None
    note_metadata: NoteMetadata | None = None
    note_content: str | None = None
    note_wc: int = 0
    logger: LoggerProtocol | None = None

    def __post_init__(self) -> None:
        self.logger = ensure_logger(self.logger, __name__)
        self.logger.debug("Création NoteContext pour %s", self.file_path)
        self.base_fp = str(Path(self.file_path).parent)
        if not self.note_metadata or not self.note_content:
            metadata, content = read_note_full(self.file_path, logger=self.logger)
            if not self.note_metadata:
                self.note_metadata = metadata
            if not self.note_content:
                self.note_content = content

        if self.note_content and self.note_wc == 0:
            self.note_wc = count_words(self.note_content, logger=self.logger)

        if not self.note_classification:
            self.note_classification = get_category_context_from_folder(folder_path=self.base_fp, logger=self.logger)

    def sync_with_db(self) -> dict[str, Any]:
        """
        Compare la note DB avec les infos recalculées (metadata, classification, contenu).

        Retourne un dict {champ: nouvelle_valeur} filtré selon _ALLOWED_COLUMNS.
        """
        self.logger = ensure_logger(self.logger, __name__)
        changes: dict[str, Any] = {}

        # --- Cas file_path (spécial move) ---
        if self.note_db.file_path != self.file_path:
            changes["file_path"] = self.file_path

        # ---- Metadata
        if self.note_metadata:
            title = sanitize_yaml_title(self.note_metadata.title)
            if title and title != self.note_db.title:
                if title.strip() == "" or title.strip().lower() == "untitled":
                    title = Path(self.file_path).stem
                    self.logger.debug("Titre vide ou None, mise à jour du titre basé sur le nom de fichier: %s", title)
                changes["title"] = title

            if self.note_metadata.summary != self.note_db.summary:
                changes["summary"] = self.note_metadata.summary

            if self.note_metadata.source != self.note_db.source:
                changes["source"] = self.note_metadata.source

            if self.note_metadata.author != self.note_db.author:
                changes["author"] = self.note_metadata.author

            if self.note_metadata.project != self.note_db.project:
                changes["project"] = self.note_metadata.project

            created = sanitize_created(self.note_metadata.created, logger=self.logger)
            if created != self.note_db.created_at:
                changes["created_at"] = created

        # ---- Classification
        if self.note_classification:
            if self.note_classification.folder_id != self.note_db.folder_id:
                changes["folder_id"] = self.note_classification.folder_id

            if self.note_classification.category_id != self.note_db.category_id:
                changes["category_id"] = self.note_classification.category_id

            if self.note_classification.subcategory_id != self.note_db.subcategory_id:
                changes["subcategory_id"] = self.note_classification.subcategory_id

            if self.note_classification.status != self.note_db.status:
                changes["status"] = self.note_classification.status

        # ---- Contenu
        if self.note_content:
            wc = count_words(self.note_content, logger=self.logger)
            if wc != self.note_db.word_count:
                changes["word_count"] = wc
                changes["content_hash"] = hash_content(self.note_content)

            if self.note_metadata and self.note_metadata.source:
                src_hash = hash_source(self.note_metadata.source)
                if src_hash != self.note_db.source_hash:
                    changes["source_hash"] = src_hash

            lang = lang_detect(self.file_path, logger=self.logger)
            if lang and lang != self.note_db.lang:
                changes["lang"] = lang

        # ---- Filtrage final
        filtered = {k: v for k, v in changes.items() if k in _ALLOWED_COLUMNS}
        if filtered != changes:
            if self.logger is not None:
                self.logger.debug("Champs ignorés car non autorisés: %s", set(changes) - set(filtered))

        return filtered

    def print_diff(self) -> None:
        """
        Compare la note DB et l'état courant du contexte.

        Affiche les différences sous forme claire (avant → après).
        """
        diffs = self.sync_with_db()
        if not diffs:
            if self.logger is not None:
                self.logger.info("Note ID=%s : aucun changement détecté", self.note_db.id)
            return

        if self.logger is not None:
            self.logger.info("Note ID=%s : changements détectés :", self.note_db.id)
        for field, new_val in diffs.items():
            old_val = getattr(self.note_db, field, None)
            if self.logger is not None:
                self.logger.info(" - %s: %r → %r", field, old_val, new_val)
