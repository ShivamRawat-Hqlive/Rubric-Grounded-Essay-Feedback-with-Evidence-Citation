"""Versioned text normalization with reversible character alignment."""

import unicodedata
from collections.abc import Iterable, Iterator

from app.services.documents.alignment import (
    MAX_ALIGNMENT_RUNS,
    OffsetRun,
    append_alignment_run,
)

NORMALIZER_VERSION = "v1"
MAX_NORMALIZED_CHARACTERS = 2_000_000
_SMART_CHARACTERS = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


def _nfc_clusters(text: str) -> Iterator[tuple[str, int, int]]:
    cluster = ""
    cluster_start = 0
    for index, character in enumerate(text):
        if not cluster:
            cluster = character
            cluster_start = index
            continue

        separate_normalization = unicodedata.normalize(
            "NFC", cluster
        ) + unicodedata.normalize("NFC", character)
        joined_normalization = unicodedata.normalize("NFC", cluster + character)
        if unicodedata.combining(character) or joined_normalization != separate_normalization:
            cluster += character
            continue

        yield cluster, cluster_start, index
        cluster = character
        cluster_start = index

    if cluster:
        yield cluster, cluster_start, len(text)


def _nfc_units(text: str) -> Iterator[tuple[str, int, int]]:
    for cluster, source_start, source_end in _nfc_clusters(text):
        normalized_cluster = unicodedata.normalize("NFC", cluster)
        if normalized_cluster == cluster:
            for offset, character in enumerate(cluster):
                yield character, source_start + offset, source_start + offset + 1
        else:
            for character in normalized_cluster:
                yield character, source_start, source_end


def _newline_units(
    units: Iterable[tuple[str, int, int]],
) -> Iterator[tuple[str, int, int]]:
    iterator = iter(units)
    pending = next(iterator, None)
    while pending is not None:
        character, source_start, source_end = pending
        pending = next(iterator, None)
        if (
            character == "\r"
            and pending is not None
            and pending[0] == "\n"
        ):
            yield "\n", source_start, pending[2]
            pending = next(iterator, None)
        else:
            yield "\n" if character == "\r" else character, source_start, source_end


def _smart_character_units(
    units: Iterable[tuple[str, int, int]],
) -> Iterator[tuple[str, int, int]]:
    for character, source_start, source_end in units:
        yield character.translate(_SMART_CHARACTERS), source_start, source_end


def _collapsed_whitespace_units(
    units: Iterable[tuple[str, int, int]],
) -> Iterator[tuple[str, int, int]]:
    iterator = iter(units)
    pending = next(iterator, None)
    while pending is not None:
        character, source_start, source_end = pending
        if character not in (" ", "\t"):
            yield character, source_start, source_end
            pending = next(iterator, None)
            continue

        pending = next(iterator, None)
        while pending is not None and pending[0] in (" ", "\t"):
            source_end = pending[2]
            pending = next(iterator, None)
        yield " ", source_start, source_end


def normalize_text(
    text: str,
    *,
    version: str = NORMALIZER_VERSION,
    max_characters: int = MAX_NORMALIZED_CHARACTERS,
) -> tuple[str, list[OffsetRun]]:
    if version != NORMALIZER_VERSION:
        raise ValueError(f"Unsupported normalizer version: {version}")
    if max_characters <= 0:
        raise ValueError("The normalization character limit must be positive.")

    units = _collapsed_whitespace_units(
        _smart_character_units(_newline_units(_nfc_units(text)))
    )
    characters: list[str] = []
    alignment: list[OffsetRun] = []
    for normalized_index, (character, source_start, source_end) in enumerate(units):
        if normalized_index >= max_characters:
            raise ValueError("The normalized document exceeds the processing limit.")
        if len(alignment) >= MAX_ALIGNMENT_RUNS and (
            not alignment or alignment[-1][1] != normalized_index
        ):
            raise ValueError("The document has too many offset transformations.")
        characters.append(character)
        append_alignment_run(
            alignment,
            normalized_index=normalized_index,
            source_start=source_start,
            source_end=source_end,
        )
    return "".join(characters), alignment
