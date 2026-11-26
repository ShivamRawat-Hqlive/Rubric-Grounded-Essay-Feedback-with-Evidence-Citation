"""Deterministic, explicitly selected provider for local demonstrations."""

import json
from decimal import Decimal

from app.services.llm.base import LLMProviderError


class MockLLMProvider:
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        try:
            rubric_context_text = system_prompt.split("RUBRIC_CONTEXT_JSON:", 1)[1]
            rubric_context, _ = json.JSONDecoder().raw_decode(
                rubric_context_text.lstrip()
            )
            criterion = rubric_context["criterion"]
            passages = json.loads(user_prompt)["untrusted_essay_passages"]
            minimum = Decimal(criterion["min_score"])
            maximum = Decimal(criterion["max_score"])
            score = float(((minimum + maximum) / 2).quantize(Decimal("0.0001")))
            evidence_quotes = []
            if passages:
                passage = passages[0]
                quote = passage["text"][:2_000]
                evidence_quotes.append(
                    {
                        "chunk_id": passage["chunk_id"],
                        "quoted_text": quote,
                        "reason": (
                            "Selected for mock demonstration; relevance is unverified."
                        ),
                    }
                )
            response = {
                "criterion_id": criterion["id"],
                "score": score,
                "rationale": (
                    "Mock demonstration score; this result is not AI-generated."
                ),
                "strengths": ["Mock demonstration feedback."],
                "weaknesses": ["Mock mode does not assess essay quality."],
                "suggestions": ["Configure OpenAI for an AI-generated evaluation."],
                "claims": [
                    {
                        "text": "Mock demonstration evidence statement.",
                        "evidence_quotes": evidence_quotes,
                    }
                ],
            }
        except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMProviderError(
                "The local mock provider could not process evaluation context."
            ) from exc
        return json.dumps(response, ensure_ascii=False)

    async def aclose(self) -> None:
        return None
