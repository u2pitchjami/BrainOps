# scripts/process_audio_manifest.py

from pathlib import Path

from brainops.ingest.audio_pipeline import process_audio_manifests

if __name__ == "__main__":
    process_audio_manifests(
        manifest_dir=Path("/mnt/unraid/Zin-progress/Brainops/audio"),
        workdir=Path("/mnt/unraid/Zin-progress/Brainops/work/audio"),
        imports_path=Path("/mnt/unraid/Zin-progress/Brainops/notes/Z_technical/imports/"),
    )
