import json
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

from brainops.utils.logger import LoggerProtocol, ensure_logger


def transcribe_audio(
    audio_path: Path,
    output_json: Path,
    model_size: str = "medium",
    language: str = "fr",
    logger: LoggerProtocol | None = None,
) -> None:
    """
    Transcribe an audio file to a JSON file with timestamps.
    """
    logger = ensure_logger(logger, __name__)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    logger.info("Loading Whisper model: %s", model_size)
    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
    )

    logger.info("Starting transcription: %s", audio_path.name)
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
    )

    result: dict[str, Any] = {
        "audio_file": audio_path.name,
        "language": info.language,
        "duration": info.duration,
        "segments": [],
    }

    for seg in segments:
        result["segments"].append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
        )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(
        "Transcription finished: %d segments written to %s",
        len(result["segments"]),
        output_json,
    )
