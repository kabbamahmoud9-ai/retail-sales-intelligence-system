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
def narrate_credit_status(customer, assessment, reorder_suggestions):
    """
    Builds a short, conversational spoken summary of a customer's
    already-persisted CreditAssessment plus their reorder suggestions.
    Reads only — never recalculates credit eligibility or trust score.
    """
    if assessment is None:
        return (
            "I don't have a credit assessment on file for you yet. "
            "Check back after your next visit to this page."
        )

    parts = []

    parts.append(
        f"You're currently a {customer.loyalty_tier} member with a trust score "
        f"of {customer.trust_score} out of 100."
    )

    parts.append(
        f"Your current credit limit is {customer.credit_limit:,.0f} leones, "
        f"with {customer.available_credit:,.0f} leones available right now."
    )

    status_phrases = {
        'eligible_increase': (
            f"Good news — you're eligible for a credit increase, up to "
            f"about {assessment.recommended_credit_limit:,.0f} leones."
        ),
        'maintain': (
            f"Your current limit looks like a good fit for now, "
            f"around {assessment.recommended_credit_limit:,.0f} leones."
        ),
        'review_needed': (
            "Your account could use a closer look before any credit changes are made."
        ),
    }
    parts.append(
        status_phrases.get(
            assessment.eligibility_status,
            "Here's where things stand with your credit."
        )
    )

    if reorder_suggestions:
        top_reorder = list(reorder_suggestions)[:2]
        names = " and ".join(item['product'].product_name for item in top_reorder)
        parts.append(f"Based on your past orders, you might want to reorder {names}.")

    parts.append("Let me know if you'd like to hear more, or head back to shopping.")

    return " ".join(parts)
def _build_recommendations_section(data):
    """
    Narrates open Critical/High priority Recommendation rows, including
    their associated DemandForecast context where available. Read-only —
    never recomputes priority, forecasts, or recommendations.

    This is the first of what will become a list of independent recap
    "sections". Future business-intelligence sources (Notifications,
    Delivery Performance, Credit Insights, etc.) can each get their own
    _build_*_section(data) function added to _RECAP_SECTION_BUILDERS
    below — this function and the recap assembly logic never need to change.
    """
    recommendations = list(data.get('recommendations') or [])
    if not recommendations:
        return None

    critical_count = sum(1 for r in recommendations if r.priority == 'critical')
    high_count = sum(1 for r in recommendations if r.priority == 'high')

    parts = []
    summary_bits = []
    if critical_count:
        summary_bits.append(f"{critical_count} critical")
    if high_count:
        summary_bits.append(f"{high_count} high priority")
    parts.append(
        f"You have {' and '.join(summary_bits)} open recommendation"
        f"{'s' if len(recommendations) != 1 else ''} that need attention."
    )

    for rec in recommendations[:3]:
        product_name = rec.product.product_name
        sentence = f"For {product_name}, {rec.recommended_action.lower().rstrip('.')}."

        forecast = getattr(rec, 'forecast', None)
        if forecast and forecast.has_sufficient_data:
            sentence = sentence.rstrip('.') + (
                f", since demand looks {forecast.trend.lower()} based on recent forecasts."
            )

        parts.append(sentence)

    remaining = len(recommendations) - min(len(recommendations), 3)
    if remaining > 0:
        parts.append(f"There are {remaining} more open item{'s' if remaining != 1 else ''} on the advisor page.")

    return " ".join(parts)


# Ordered list of recap sections. To add a new business-intelligence
# source to the staff advisor recap later, write a new
# _build_*_section(data) function and append it here — nothing else
# in narrate_advisor_recap() needs to change.
_RECAP_SECTION_BUILDERS = [
    _build_recommendations_section,
    # Future: _build_notifications_section,
    # Future: _build_delivery_section,
    # Future: _build_credit_section,
]


def narrate_advisor_recap(data):
    """
    Builds a spoken business recap from a dict of already-fetched data.
    Each section reads its own key from `data` and returns a spoken
    paragraph, or None if there's nothing to report for that section.
    """
    sections = [
        text for builder in _RECAP_SECTION_BUILDERS
        if (text := builder(data))
    ]

    if not sections:
        return (
            "Everything looks under control right now — there are no open "
            "critical or high priority recommendations to report."
        )

    return " ".join(sections)