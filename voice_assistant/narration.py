"""
voice_assistant/narration.py

Narration helpers for the Voice Assistant.

Presentation layer ONLY: turns already-computed, already-persisted
data (ShoppingRecommendation, CreditAssessment, DemandForecast,
advisor.Recommendation, Notification, delivery stats, etc.) into
short, natural-sounding spoken summaries. This module never performs
business calculations, scoring, or generates new recommendations —
it only reads and rephrases what already exists.
"""

import random

_INTROS = [
    "Here's what I found for you.",
    "I've got a few suggestions based on what you asked for.",
    "Okay, here's what looks like a good fit.",
]

_LIST_CONNECTORS = [
    "First up, {name} — {reason}.",
    "I'd also suggest {name}, since {reason}.",
    "Another good option is {name}: {reason}.",
]

_CLOSINGS = [
    "Let me know if you'd like me to add these to your cart, or if you want to try a different request.",
    "You can add any of these to your cart, or ask me for something different.",
]


def _clean_reason(reasoning_text):
    """
    Lightly reformats an existing reasoning string for spoken delivery
    (lowercases the leading letter, strips a trailing period) without
    changing its actual content or meaning.
    """
    text = (reasoning_text or "").strip().rstrip('.')
    if text and text[0].isupper():
        text = text[0].lower() + text[1:]
    return text or "it matches what you're looking for"


def narrate_shopping_recommendations(session, recommendations):
    """
    Builds a short, conversational spoken summary of an already-persisted
    set of ShoppingRecommendation rows for one ShoppingSession.
    Reads only — never recomputes rankings, scores, or reasoning.
    """
    recommendations = list(recommendations)

    if not recommendations:
        return (
            "I couldn't find any matching products for that request right now. "
            "You might want to try describing what you need a little differently."
        )

    top_items = recommendations[:3]
    total_count = len(recommendations)

    parts = [random.choice(_INTROS)]
    parts.append(
        f"I found {total_count} item{'s' if total_count != 1 else ''} "
        f"that should work well for you."
    )

    for i, rec in enumerate(top_items):
        reason = _clean_reason(rec.reasoning)
        template = _LIST_CONNECTORS[i % len(_LIST_CONNECTORS)]
        parts.append(template.format(name=rec.product.product_name, reason=reason))

    if total_count > len(top_items):
        remaining = total_count - len(top_items)
        parts.append(
            f"There are {remaining} more option{'s' if remaining != 1 else ''} "
            f"waiting for you on the results page."
        )

    parts.append(random.choice(_CLOSINGS))
    return " ".join(parts)