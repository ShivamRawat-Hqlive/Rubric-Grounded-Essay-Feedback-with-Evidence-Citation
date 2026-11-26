"""Sentence-level chunking with stable character offsets."""

from dataclasses import dataclass
from functools import lru_cache

from spacy.lang.en import English


@dataclass(frozen=True)
class SentenceChunk:
    sentence_index: int
    char_start: int
    char_end: int
    text: str


@lru_cache(maxsize=1)
def _sentencizer() -> English:
    nlp = English()
    nlp.add_pipe("sentencizer")
    return nlp


def split_sentences(text: str) -> list[SentenceChunk]:
    if not text:
        return []
    nlp = _sentencizer()
    if len(text) >= nlp.max_length:
        nlp.max_length = len(text) + 1

    chunks: list[SentenceChunk] = []
    for sentence_index, sentence in enumerate(nlp(text).sents):
        start = sentence.start_char
        end = sentence.end_char
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            chunks.append(
                SentenceChunk(
                    sentence_index=sentence_index,
                    char_start=start,
                    char_end=end,
                    text=text[start:end],
                )
            )
    return chunks
