# brainops/ingest/audio_download.py

from pathlib import Path

from yt_dlp import YoutubeDL

from brainops.utils.logger import LoggerProtocol, ensure_logger


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
