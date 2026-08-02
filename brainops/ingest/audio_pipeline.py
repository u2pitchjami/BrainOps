# brainops/ingest/audio_pipeline.py

from pathlib import Path
import re
import shutil

from brainops.embeddings.emb_main import process_transcript_embeddings
from brainops.embeddings.ollama_provider import OllamaEmbeddingProvider
from brainops.embeddings.repositories.temp_blocks_repository import TempBlocksEmbeddingRepository
from brainops.ingest.audio_download import download_audio, find_audio_file, find_audio_for_manifest
from brainops.ingest.audio_manifest import load_manifest
from brainops.ingest.builder_note import build_note_shell_from_audio_manifest
from brainops.ingest.generate_markdown import generate_markdown_from_whisper
from brainops.ingest.mapping import build_metadata_from_audio_manifest
from brainops.ingest.media_builder import build_media_from_manifest
from brainops.ingest.transcribe import is_valid_transcription, transcribe_audio
from brainops.io.note_writer import write_metadata_to_note
from brainops.io.read_note import read_note_content
from brainops.sql.notes.db_medias import upsert_media_from_model
from brainops.sql.notes.db_update_notes import update_obsidian_note
from brainops.sql.notes.db_upsert_note import upsert_note_from_model
from brainops.utils.config import IMPORTS_PATH, MANIFEST_DIR, MODEL_EMBEDDINGS, WORK_DIR
from brainops.utils.logger import get_logger

logger = get_logger("Brainops Audio Pipeline")


def slugi(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value)
    return value.strip("-")


def process_audio_manifests(
    manifest_dir: Path = Path(MANIFEST_DIR),
    workdir: Path = Path(WORK_DIR),
    imports_path: Path = Path(IMPORTS_PATH),
    *,
    force_download: bool = False,
    force_transcription: bool = False,
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
    logger.info("Found %d manifest(s) to process.", len(list(manifest_dir.glob("*.yml"))))
    for manifest_path in sorted(manifest_dir.glob("*.yml")):
        try:
            logger.info("Processing manifest: %s", manifest_path.name)
            manifest = load_manifest(manifest_path)
            logger.info("Loaded manifest: %s by %s", manifest["title"], ", ".join(manifest["authors"]))
            logger.debug("Manifest content: %s", manifest)

            published_at = manifest["published_at"]
            title = manifest["title"]
            language = manifest.get("language", "fr")

            folder_name = f"{published_at}-{slugi(title)}"
            output_dir = workdir / folder_name
            output_dir.mkdir(parents=True, exist_ok=True)

            # --- Audio acquisition ---
            audio_file = find_audio_file(output_dir)

            if audio_file is not None:
                logger.info(
                    "Audio already present in work directory, download skipped: %s",
                    audio_file,
                )
            else:
                imported_audio = find_audio_for_manifest(manifest_path)

                if imported_audio is not None:
                    destination = output_dir / imported_audio.name

                    try:
                        audio_file = Path(
                            shutil.move(
                                imported_audio.as_posix(),
                                destination.as_posix(),
                            )
                        )
                    except OSError as exc:
                        raise RuntimeError(
                            f"Impossible de déplacer l'audio {imported_audio} vers {destination}"
                        ) from exc

                    logger.info(
                        "Local audio moved from manifest directory: %s -> %s",
                        imported_audio,
                        audio_file,
                    )
                else:
                    audio_file = download_audio(
                        url=manifest["source"]["url"],
                        title=title,
                        published_at=published_at,
                        output_dir=output_dir,
                        logger=logger,
                    )

                    logger.info("Audio downloaded: %s", audio_file)

            # --- Transcription ---
            transcription_path = output_dir / "transcription.json"
            normalized_json_path = output_dir / "normalized_transcription.json"
            if not force_transcription and is_valid_transcription(transcription_path):
                logger.info(
                    "Valid transcription already present, transcription skipped: %s",
                    transcription_path,
                )
            else:
                transcribe_audio(
                    audio_path=audio_file,
                    output_json=transcription_path,
                    model_size="medium",
                    language=language,
                    logger=logger,
                )
                logger.info(
                    "Transcription completed: %s",
                    transcription_path,
                )

            # --- Markdown generation ---
            markdown_filename = f"{title}.md"
            markdown_path = output_dir / markdown_filename

            transcript = generate_markdown_from_whisper(
                whisper_json_path=transcription_path,
                output_md=markdown_path,
                normalized_json_path=Path(normalized_json_path),
                title=title,
                manifest=manifest,
                audio_file=audio_file,
                logger=logger,
            )
            logger.info("Markdown generated: %s", markdown_path)

            note_metadata = build_metadata_from_audio_manifest(manifest=manifest, media_file_path=audio_file)

            logger.info(
                "NoteMetadata built %s",
                extra={
                    "note_title": note_metadata.title,
                    "note_author": note_metadata.author,
                    "note_source": note_metadata.source,
                    "note_created": note_metadata.created,
                    "note_doc_type": note_metadata.doc_type,
                    "note_analysis_profile": note_metadata.analysis_profile,
                },
            )

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
                doc_type=note_metadata.doc_type,
                analysis_profile=note_metadata.analysis_profile,
                provider=note_metadata.provider,
                logger=logger,
            )

            note_id = upsert_note_from_model(note=note, logger=logger)

            media = build_media_from_manifest(
                note_id=note_id,
                manifest=manifest,
                media_file_path=audio_file,
                doc_type=note_metadata.doc_type,
                logger=logger,
            )

            media_id = upsert_media_from_model(media)

            embedding_result = process_transcript_embeddings(
                media_id=media_id,
                transcript=transcript,
                model_name=MODEL_EMBEDDINGS,
                provider=OllamaEmbeddingProvider(),
                repository=TempBlocksEmbeddingRepository(),
                resume_if_possible=True,
            )
            logger.debug(f"embedding_result = {embedding_result}")

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
