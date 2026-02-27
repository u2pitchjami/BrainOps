# brainops/ingest/audio_pipeline.py

from pathlib import Path
import re
import shutil

from brainops.ingest.audio_download import download_audio
from brainops.ingest.audio_manifest import load_manifest
from brainops.ingest.builder_note import build_note_shell_from_audio_manifest
from brainops.ingest.generate_markdown import generate_markdown_from_whisper
from brainops.ingest.mapping import build_metadata_from_audio_manifest
from brainops.ingest.media_builder import build_media_from_manifest
from brainops.ingest.transcribe import transcribe_audio
from brainops.io.note_writer import write_metadata_to_note
from brainops.io.read_note import read_note_content
from brainops.sql.notes.db_medias import upsert_media_from_model
from brainops.sql.notes.db_update_notes import update_obsidian_note
from brainops.sql.notes.db_upsert_note import upsert_note_from_model
from brainops.utils.config import IMPORTS_PATH, MANIFEST_DIR, WORK_DIR
from brainops.utils.logger import get_logger

logger = get_logger("Brainops Audio Pipeline")


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-")


def process_audio_manifests(
    manifest_dir: Path = Path(MANIFEST_DIR),
    workdir: Path = Path(WORK_DIR),
    imports_path: Path = Path(IMPORTS_PATH),
) -> list[Path]:
    """
    Traite tous les manifests audio :
    - télécharge l'audio
    - transcrit avec Whisper
    - génère la note Markdown
    - déplace le manifest dans le dossier final
    - copie la note Markdown dans IMPORTS_PATH
    """
    logger.info("Processing audio manifests in %s...", manifest_dir)
    if not manifest_dir.is_dir():
        logger.error("%s is not a directory.", manifest_dir)
        raise ValueError(f"{manifest_dir} n'est pas un dossier")

    # imports_path.mkdir(parents=True, exist_ok=True)
    # logger.info("Output will be saved to %s, Markdown copies to %s", workdir, imports_path)

    audio_files: list[Path] = []
    logger.info("Found %d manifest(s) to process.", len(list(manifest_dir.glob("*.yaml"))))
    for manifest_path in sorted(manifest_dir.glob("*.yaml")):
        try:
            logger.info("Processing manifest: %s", manifest_path.name)
            manifest = load_manifest(manifest_path)
            logger.info("Loaded manifest: %s by %s", manifest["title"], ", ".join(manifest["authors"]))

            published_at = manifest["published_at"]
            title = manifest["title"]
            language = manifest.get("language", "fr")

            folder_name = f"{published_at}-{slugify(title)}"
            output_dir = workdir / folder_name
            output_dir.mkdir(parents=True, exist_ok=True)

            # --- Download audio ---
            audio_file = download_audio(
                url=manifest["source"]["url"],
                title=title,
                published_at=published_at,
                output_dir=output_dir,
                logger=logger,
            )
            logger.info("Audio downloaded: %s", audio_file)

            note_metadata = build_metadata_from_audio_manifest(manifest=manifest, media_file_path=audio_file)

            logger.info(
                "NoteMetadata built",
                extra={
                    "note_title": note_metadata.title,
                    "note_author": note_metadata.author,
                    "note_source": note_metadata.source,
                    "note_created": note_metadata.created,
                },
            )

            # --- Transcription ---
            transcription_path = output_dir / "transcription.json"
            transcribe_audio(
                audio_path=audio_file,
                output_json=transcription_path,
                model_size="medium",
                language=language,
                logger=logger,
            )
            logger.info("Transcription completed: %s", transcription_path)

            # --- Markdown generation ---
            markdown_filename = f"{slugify(title)}.md"
            markdown_path = output_dir / markdown_filename

            generate_markdown_from_whisper(
                whisper_json_path=transcription_path,
                output_md=markdown_path,
                title=title,
                manifest=manifest,
                audio_file=audio_file,
                logger=logger,
            )
            logger.info("Markdown generated: %s", markdown_path)

            content = read_note_content(filepath=markdown_path, logger=logger)
            write_metadata_to_note(
                filepath=markdown_path,
                content=content,
                metadata=note_metadata,
                logger=logger,
            )

            note = build_note_shell_from_audio_manifest(
                title=manifest["title"],
                file_path=markdown_path,
                source_url=manifest["source"]["url"],
                created_at=manifest.get("published_at"),
                language=manifest.get("language"),
                logger=logger,
            )

            note_id = upsert_note_from_model(note=note, logger=logger)

            media = build_media_from_manifest(
                note_id=note_id,
                manifest=manifest,
                media_file_path=audio_file,
                semantic_type=note_metadata.doc_type,
                logger=logger,
            )

            media_id = upsert_media_from_model(media)

            # --- Copy Markdown to IMPORTS_PATH ---
            imports_md_path = imports_path / markdown_filename

            updates = {
                "file_path": imports_md_path,
                "media_id": media_id,
            }

            update_obsidian_note(note_id, updates)

            shutil.copy2(markdown_path, imports_md_path)
            logger.info("Markdown copied to imports: %s", imports_md_path)

            # --- Move manifest into output_dir ---
            final_manifest_path = output_dir / "manifest.yml"
            manifest_path.rename(final_manifest_path)
            logger.info("Manifest moved to: %s", final_manifest_path)

            audio_files.append(audio_file)

        except Exception:
            logger.exception("Failed to process manifest %s", manifest_path.name)
            continue

    return audio_files
