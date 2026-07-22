# brainops/ingest/audio_download.py

from pathlib import Path

from yt_dlp import YoutubeDL

from brainops.utils.logger import LoggerProtocol, ensure_logger

AUDIO_EXTENSIONS: tuple[str, ...] = (
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".opus",
    ".ogg",
    ".webm",
)


def find_audio_for_manifest(manifest_path: Path) -> Path | None:
    """
    Recherche un audio portant le même nom de base que le manifest.
    """

    for extension in AUDIO_EXTENSIONS:
        candidate = manifest_path.with_suffix(extension)

        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate

    return None


def find_audio_file(directory: Path) -> Path | None:
    """
    Recherche un unique fichier audio non vide dans un dossier.
    """

    if not directory.is_dir():
        return None

    candidates = sorted(
        path
        for path in directory.iterdir()
        if (path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS and path.stat().st_size > 0)
    )

    if not candidates:
        return None

    if len(candidates) > 1:
        raise ValueError(
            f"Plusieurs fichiers audio trouvés dans {directory} : {', '.join(path.name for path in candidates)}"
        )

    return candidates[0]


def download_audio(
    url: str,
    title: str,
    output_dir: Path,
    published_at: str,
    logger: LoggerProtocol | None = None,
) -> Path:
    logger = ensure_logger(logger, __name__)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_title = "".join(c for c in title.lower().replace(" ", "_") if c.isalnum() or c in "_-")

    outtmpl = str(output_dir / f"{safe_title}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return Path(filename).with_suffix(".mp3")

    except Exception as exc:
        logger.exception("yt-dlp failed for %s", url)
        raise RuntimeError("Audio download failed") from exc
