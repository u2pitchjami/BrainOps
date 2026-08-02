from collections.abc import Sequence
from math import ceil
from typing import TypeVar

TARGET_SEGMENT_DURATION_MINUTES = 60.0
T = TypeVar("T")


def calculate_segment_count(
    duration_minutes: float,
) -> int:
    """
    Calcule le nombre de segments d'environ une heure.
    """
    if duration_minutes <= 0:
        raise ValueError("duration_minutes doit être strictement positive")

    return max(
        1,
        ceil(duration_minutes / TARGET_SEGMENT_DURATION_MINUTES),
    )


def split_evenly[T](
    items: Sequence[T],
    segment_count: int,
) -> list[list[T]]:
    """
    Répartit une séquence en segments de tailles aussi proches que possible.

    L'ordre initial des éléments est conservé.
    """
    if segment_count <= 0:
        raise ValueError("segment_count doit être strictement positif")

    if not items:
        return []

    effective_segment_count = min(
        segment_count,
        len(items),
    )
    base_size, remainder = divmod(
        len(items),
        effective_segment_count,
    )

    segments: list[list[T]] = []
    start_index = 0

    for segment_index in range(effective_segment_count):
        segment_size = base_size + (1 if segment_index < remainder else 0)
        end_index = start_index + segment_size

        segments.append(list(items[start_index:end_index]))
        start_index = end_index

    return segments
