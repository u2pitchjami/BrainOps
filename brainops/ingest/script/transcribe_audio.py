from pathlib import Path

from brainops.ingest.transcribe import transcribe_audio

if __name__ == "__main__":
    transcribe_audio(
        audio_path=Path("/mnt/unraid/Zin-progress/Brainops/work/audio/que_reste-t-il_du_mitterrandisme_.mp3"),
        output_json=Path("/mnt/unraid/Zin-progress/Brainops/work/audio/transcription.json"),
    )
