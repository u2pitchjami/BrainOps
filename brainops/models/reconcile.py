from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypedDict


class Severity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class CheckConfig:
    base_path: Path
    base_notes: Path
    out_dir: Path


class NoteRow(TypedDict):
    id: int
    file_path: str
    status: str
    source_hash: str | None


@dataclass
class ApplyStats:
    added_notes: int = 0
    deleted_notes: int = 0
    errors: int = 0


@dataclass(frozen=True)
class DiffSets:
    notes_missing_in_db: list[str]
    notes_missing_file: list[str]


@dataclass
class Anomaly:
    severity: Severity
    code: str
    message: str
    note_ids: tuple[int, ...]
    paths: tuple[str, ...]
    fixed: bool = False


@dataclass
class FixStats:
    parent_links_fixed: int = 0
    categories_fixed: int = 0
