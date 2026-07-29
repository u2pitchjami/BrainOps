"""
# models/event.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import time
from typing import Literal, NotRequired, TypedDict

from brainops.models.note import Note

EventAction = Literal["created", "deleted", "modified", "moved", "reconcile", "audio"]
EventType = Literal["file", "directory", "script"]


class QueueTask(StrEnum):
    IMPORT = "import"
    CHECK_EMBEDDING = "check_embedding"


class DirEvent(TypedDict, total=True):
    """
    DirEvent _summary_

    _extended_summary_

    Args:
        TypedDict (_type_): _description_
        total (bool, optional): _description_. Defaults to True.
    """

    type: Literal["directory"]
    action: EventAction
    path: str
    src_path: NotRequired[str]


class Event(TypedDict, total=True):
    """
    Event _summary_

    _extended_summary_

    Args:
        TypedDict (_type_): _description_
        total (bool, optional): _description_. Defaults to True.
    """

    type: EventType
    action: EventAction
    path: str
    # Clés optionnelles selon action/type
    task: NotRequired[QueueTask]
    src_path: NotRequired[str]
    Note: NotRequired[Note | None]
    new_path: NotRequired[str]  # legacy (si jamais encore utilisé)


@dataclass(slots=True)
class QueuedNoteContext:
    """
    Technical wrapper for a queued processing unit.
    """

    event: Event
    note: Note | None
    lock_key: str | None

    created_at: float = field(default_factory=time.time)
    retry_count: int = 0
