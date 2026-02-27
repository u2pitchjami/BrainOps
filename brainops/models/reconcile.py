from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TypedDict


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class CheckConfig:
    base_path: Path
    base_notes: Path
    out_dir: Path


class FolderRow(TypedDict):
    id: int
    path: str
    folder_type: str | None
    category_id: int
    subcategory_id: int | None


class CategoryRow(TypedDict):
    id: int
    name: str
    description: str | None
    prompt_name: str | None
    parent_id: int | None


class NoteRow(TypedDict):
    id: int
    parent_id: int | None
    file_path: str
    category_id: int
    subcategory_id: int | None
    status: str
    folder_id: int
    source_hash: str | None


@dataclass
class ApplyStats:
    added_folders: int = 0
    deleted_folders: int = 0
    added_notes: int = 0
    deleted_notes: int = 0
    errors: int = 0


@dataclass(frozen=True)
class DiffSets:
    folders_missing_in_db: list[str]
    folders_ghost_in_db: list[str]
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
