"""Compact mappings between normalized and extracted character offsets."""

from collections.abc import Sequence

OffsetRun = list[int]
MAX_ALIGNMENT_RUNS = 250_000


class AlignmentTooComplexError(ValueError):
    """Raised when an offset map would exceed its storage bound."""


def append_alignment_run(
    runs: list[OffsetRun],
    *,
    normalized_index: int,
    source_start: int,
    source_end: int,
) -> None:
    if source_start < 0 or source_end <= source_start:
        raise ValueError("Invalid source span in offset alignment.")
    if (
        source_end - source_start == 1
        and runs
        and runs[-1][1] == normalized_index
        and runs[-1][3] == source_start
        and runs[-1][1] - runs[-1][0] == runs[-1][3] - runs[-1][2]
    ):
        runs[-1][1] += 1
        runs[-1][3] = source_end
        return
    runs.append([normalized_index, normalized_index + 1, source_start, source_end])
    if len(runs) > MAX_ALIGNMENT_RUNS:
        raise AlignmentTooComplexError("The document has too many offset transformations.")


def compress_alignment(
    character_spans: Sequence[tuple[int, int]],
) -> list[OffsetRun]:
    runs: list[OffsetRun] = []
    for normalized_index, (source_start, source_end) in enumerate(character_spans):
        append_alignment_run(
            runs,
            normalized_index=normalized_index,
            source_start=source_start,
            source_end=source_end,
        )
    return runs


def map_normalized_span(
    alignment: Sequence[Sequence[int]],
    start: int,
    end: int,
) -> tuple[int, int]:
    if start < 0 or end <= start:
        raise ValueError("Normalized span must be a non-empty half-open range.")

    source_starts: list[int] = []
    source_ends: list[int] = []
    for normalized_start, normalized_end, source_start, source_end in alignment:
        overlap_start = max(start, normalized_start)
        overlap_end = min(end, normalized_end)
        if overlap_start >= overlap_end:
            continue
        if normalized_end - normalized_start == source_end - source_start:
            source_starts.append(source_start + overlap_start - normalized_start)
            source_ends.append(source_start + overlap_end - normalized_start)
        else:
            source_starts.append(source_start)
            source_ends.append(source_end)

    if not source_starts:
        raise ValueError("Normalized span is not covered by the offset alignment.")
    return min(source_starts), max(source_ends)


def map_source_span_to_normalized(
    alignment: Sequence[Sequence[int]],
    start: int,
    end: int,
) -> tuple[int, int]:
    if start < 0 or end < start:
        raise ValueError("Source span must be a non-negative half-open range.")

    normalized_starts: list[int] = []
    normalized_ends: list[int] = []
    for normalized_start, normalized_end, source_start, source_end in alignment:
        if source_start < end and start < source_end:
            if normalized_end - normalized_start == source_end - source_start:
                overlap_start = max(start, source_start)
                overlap_end = min(end, source_end)
                normalized_starts.append(
                    normalized_start + overlap_start - source_start
                )
                normalized_ends.append(normalized_start + overlap_end - source_start)
            else:
                normalized_starts.append(normalized_start)
                normalized_ends.append(normalized_end)

    if normalized_starts:
        return min(normalized_starts), max(normalized_ends)

    insertion_point = 0
    for normalized_start, normalized_end, _, source_end in alignment:
        if source_end <= start:
            insertion_point = max(insertion_point, normalized_end)
        elif normalized_start == 0:
            break
    return insertion_point, insertion_point
