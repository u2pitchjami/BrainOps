"""
# check_duplicate.py
"""

from __future__ import annotations

from enum import StrEnum
import re


class BrainopsSection(StrEnum):
    SUMMARY = "SUMMARY"
    QUESTIONS = "QUESTIONS"
    GLOSSARY = "GLOSSARY"
    ORIGINAL = "ORIGINAL"


def extract_brainops_section(note_body: str, section: BrainopsSection) -> str | None:
    """
    Extrait une section BrainOps depuis une note Markdown.

    Exemple de section :
    <!-- BRAINOPS_SUMMARY_START -->
    contenu
    <!-- BRAINOPS_SUMMARY_END -->
    """
    start_marker = f"<!-- BRAINOPS_{section.value}_START -->"
    end_marker = f"<!-- BRAINOPS_{section.value}_END -->"
    print(f"Extracting section {section.value} with markers {start_marker} and {end_marker}")
    pattern = re.compile(
        rf"{re.escape(start_marker)}(.*?){re.escape(end_marker)}",
        re.DOTALL,
    )
    print(f"Using pattern: {pattern.pattern}")
    match = pattern.search(note_body)
    print(f"Match found: {bool(match)}")
    if match is None:
        return None

    return match.group(1).strip()
