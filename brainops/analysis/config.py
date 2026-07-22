"""
# models/analysis.py
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AnalysisConfig:
    profile: str = "generic"
    selection_mode: str = "standard"

    context: str | None = None
    objective: str | None = None
    perspective: str | None = None

    instructions: list[str] = field(default_factory=list)
    reflection_questions: list[str] = field(default_factory=list)
