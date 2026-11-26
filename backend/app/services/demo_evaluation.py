"""Transparent, deterministic evaluation for the local portfolio demonstration."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import uuid4

from app.services.documents.pipeline import ProcessedDocument


@dataclass(frozen=True)
class DemoCriterion:
    name: str
    description: str
    weight: int
    indicators: tuple[str, ...]
    strength: str
    weakness: str
    suggestion: str


DEMO_RUBRIC = (
    DemoCriterion(
        name="Content and relevance",
        description="Develops the topic with enough relevant supporting detail.",
        weight=20,
        indicators=("example", "evidence", "detail", "topic", "support"),
        strength="The essay includes developed content to discuss.",
        weakness="The essay is brief, so its development is limited.",
        suggestion="Add specific examples and explain how they support the topic.",
    ),
    DemoCriterion(
        name="Grammar and vocabulary",
        description="Uses varied vocabulary and readable sentence construction.",
        weight=20,
        indicators=("word", "language", "grammar", "sentence", "vocabulary"),
        strength="The essay provides enough language for a vocabulary variety check.",
        weakness="Repeated or limited wording may make the essay less expressive.",
        suggestion="Proofread sentence boundaries and replace repeated words with precise alternatives.",
    ),
    DemoCriterion(
        name="Essay structure",
        description="Organizes ideas into paragraphs with a clear opening and ending.",
        weight=20,
        indicators=("first", "finally", "conclusion", "introduction", "paragraph"),
        strength="Paragraph breaks give the response visible organization.",
        weakness="The essay has few paragraph or conclusion signals.",
        suggestion="Use an opening claim, focused body paragraphs, and a concluding paragraph.",
    ),
    DemoCriterion(
        name="Critical thinking",
        description="Explains reasons, consequences, or more than one perspective.",
        weight=20,
        indicators=("because", "however", "although", "therefore", "reason", "impact"),
        strength="Reasoning and contrast markers appear in the essay.",
        weakness="The essay shows few explicit reasoning or alternative-view signals.",
        suggestion="Explain why each piece of evidence matters and consider another perspective.",
    ),
    DemoCriterion(
        name="Clarity and coherence",
        description="Connects ideas with clear transitions and readable sentence lengths.",
        weight=20,
        indicators=("also", "however", "therefore", "for example", "in addition", "because"),
        strength="The essay uses connecting language to link ideas.",
        weakness="Few explicit transitions are present between ideas.",
        suggestion="Add transitions where the relationship between ideas may be unclear.",
    ),
)

_WORD_PATTERN = re.compile(r"\b[\w'-]+\b", re.UNICODE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
def _score_for(criterion: DemoCriterion, text: str, words: list[str]) -> tuple[int, str]:
    lowered = text.casefold()
    word_count = len(words)
    if criterion.name == "Content and relevance":
        score = 1 if word_count < 40 else 2 if word_count < 90 else 3 if word_count < 180 else 4
        basis = f"Demo length heuristic: {word_count} words."
    elif criterion.name == "Grammar and vocabulary":
        unique_ratio = len(set(word.casefold() for word in words)) / max(word_count, 1)
        score = 1 if word_count < 20 else 2 if unique_ratio < 0.35 else 3 if unique_ratio < 0.5 else 4
        basis = f"Demo vocabulary-variety heuristic: {unique_ratio:.0%} unique-word ratio."
    elif criterion.name == "Essay structure":
        paragraph_count = sum(bool(part.strip()) for part in re.split(r"\n\s*\n", text))
        structure_signals = sum(term in lowered for term in ("introduction", "in conclusion", "finally"))
        score = min(5, 1 + min(paragraph_count, 3) + structure_signals)
        basis = f"Demo structure heuristic: {paragraph_count} paragraphs and {structure_signals} signposts."
    elif criterion.name == "Critical thinking":
        reasoning_signals = sum(
            len(re.findall(rf"\b{re.escape(term)}\b", lowered))
            for term in ("because", "however", "although", "therefore", "reason", "impact")
        )
        score = min(5, 1 + reasoning_signals)
        basis = f"Demo reasoning-marker heuristic: {reasoning_signals} markers."
    else:
        sentences = [item for item in _SENTENCE_SPLIT.split(text) if item.strip()]
        transitions = sum(
            len(re.findall(rf"\b{re.escape(term)}\b", lowered))
            for term in ("also", "however", "therefore", "for example", "in addition", "because")
        )
        average_length = word_count / max(len(sentences), 1)
        score = min(5, 1 + min(transitions, 2) + int(8 <= average_length <= 24))
        basis = (
            f"Demo cohesion heuristic: {transitions} transition markers and "
            f"{average_length:.1f} words per sentence."
        )
    return max(1, min(5, score)), basis


def _evidence_quote(
    text: str,
    document: ProcessedDocument,
    criterion: DemoCriterion,
) -> dict[str, object] | None:
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    if not sentences:
        candidate = text.strip()[:240]
    else:
        candidate = max(
            sentences,
            key=lambda sentence: sum(
                bool(re.search(rf"\b{re.escape(term)}\b", sentence, re.IGNORECASE))
                for term in criterion.indicators
            ),
        )[:240]
    if not candidate:
        return None

    start = text.find(candidate)
    if start < 0:
        return None
    end = start + len(candidate)
    page_number = next(
        (
            page.page_number
            for page in document.page_map
            if page.page_number is not None
            and page.extracted_char_start < end
            and start < page.extracted_char_end
        ),
        None,
    )
    return {
        "quoted_text": candidate,
        "extracted_char_start": start,
        "extracted_char_end": end,
        "page_number": page_number,
        "existence_verified": text[start:end] == candidate,
    }


def create_demo_evaluation(
    document: ProcessedDocument,
    *,
    filename: str,
) -> dict[str, object]:
    text = document.extracted_text
    words = _WORD_PATTERN.findall(text)
    criterion_results: list[dict[str, object]] = []
    weighted_score = 0.0
    for criterion in DEMO_RUBRIC:
        score, basis = _score_for(criterion, text, words)
        citation = _evidence_quote(text, document, criterion)
        strength = (
            criterion.strength
            if score >= 3
            else "A draft is available for faculty discussion."
        )
        criterion_results.append(
            {
                "name": criterion.name,
                "description": criterion.description,
                "weight_percent": criterion.weight,
                "score": score,
                "max_score": 5,
                "weighted_score": round(score * criterion.weight / 100, 2),
                "basis": basis,
                "strengths": [strength],
                "areas_to_improve": [criterion.weakness],
                "suggestions": [criterion.suggestion],
                "evidence_quotes": [citation] if citation else [],
            }
        )
        weighted_score += score * criterion.weight / 100

    return {
        "id": str(uuid4()),
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_mode": "local_demo",
        "demo_label": "DEMO-GENERATED — NOT AI",
        "status": "needs_review",
        "extracted_text": text,
        "extractor_name": document.extractor_name,
        "page_map": [
            {
                "page_number": page.page_number,
                "extracted_char_start": page.extracted_char_start,
                "extracted_char_end": page.extracted_char_end,
                "extraction_method": page.extraction_method,
            }
            for page in document.page_map
        ],
        "total_score": round(weighted_score, 2),
        "max_total_score": 5,
        "criteria": criterion_results,
        "faculty_note": None,
    }


def verify_demo_citations(evaluation: dict[str, object]) -> bool:
    text = str(evaluation["extracted_text"])
    for criterion in evaluation["criteria"]:
        for citation in criterion["evidence_quotes"]:
            start = citation["extracted_char_start"]
            end = citation["extracted_char_end"]
            quote = citation["quoted_text"]
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or not isinstance(quote, str)
                or start < 0
                or end <= start
                or end > len(text)
                or text[start:end] != quote
            ):
                return False
            citation["existence_verified"] = True
    return True
