# brainops/ingest/audio_manifest.py

from pathlib import Path
from typing import TypedDict

import yaml


class SourceInfo(TypedDict):
    url: str
    type: str
    provider: str
    show: str


class AudioManifest(TypedDict):
    manifest_version: int
    source: SourceInfo
    title: str
    language: str
    published_at: str
    authors: list[str]


def load_manifest(path: Path) -> AudioManifest:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8") as f:
        data: AudioManifest = yaml.safe_load(f)

    return data


class WhisperSegment(TypedDict):
    text: str


class WhisperMetadata(TypedDict, total=False):
    language: str
    duration: float
    audio_file: str


class WhisperJSON(TypedDict):
    segments: list[WhisperSegment]
