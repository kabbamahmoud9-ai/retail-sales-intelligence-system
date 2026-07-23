"""
ai_commerce/conversational.py

Orchestration layer for the Conversational Shopping AI (Step 17, Mode 4).
Contains ZERO business logic of its own — every actual decision (product
ranking, credit eligibility, visual similarity, churn/segment insight,
delivery fee) is delegated to the existing service functions already
built in ai_commerce.services, visual_search.services,
customer_insights.services, and delivery.models.

This file's only job: classify what the customer is asking about (intent
detection, rule-based/NLTK — no new NLP engine), maintain lightweight
multi-turn context (slot-filling), route to the correct existing
function, and wrap the result in a natural-language reply using
template-based generation (same pattern as customer_insights'
generate_summary_text()).

The Gemini seam (llm_adapter.py, built in 17c) plugs in here and ONLY
here — if CONVERSATIONAL_AI_BACKEND='gemini', intent classification
and/or reply generation route through the adapter instead. Everything
downstream (which existing service gets called) stays identical either
way, since the adapter only ever affects understanding/phrasing, never
which business function answers the question.
"""
import re
from django.conf import settings

from .models import ConversationSession, ConversationTurn, ShoppingSession
from .services import (
    _tokenize_and_lemmatize, get_candidate_products, generate_shopping_recommendations,
    calculate_credit_recommendation, get_reorder_suggestions,
)

CONVERSATIONAL_VERSION = "v1-rule-based"

# ---------------------------------------------------------------------------
# Intent classification — rule-based keyword/pattern matching, extending
# the same NLTK tokenize/lemmatize pipeline services.py already uses.
# Not a new NLP engine; reuses _tokenize_and_lemmatize() directly.
# ---------------------------------------------------------------------------

_INTENT_PATTERNS = {
    'credit_question':    {'credit', 'loan', 'limit', 'afford', 'owe', 'debt'},
    'reorder_question':   {'again', 'usual', 'reorder', 'previous', 'before', 'last time'},
    'insight_question':   {'loyal', 'vip', 'segment', 'churn', 'history', 'spending'},
    'delivery_question':  {'deliver', 'delivery', 'shipping', 'arrive', 'zone'},
    'greeting':           {'hello', 'hi', 'hey', 'good morning', 'good afternoon'},
}


def _classify_intent(message_text):
    """
    Returns one of _INTENT_PATTERNS' keys, or 'shopping_query' as the
    default fallback (most messages are genuinely product requests).

    Checks BOTH the lemmatized/stopword-filtered token set (for genuine
    content words) AND the raw lowercased message (for short, common
    trigger words like "before"/"again" that NLTK's stopword list would
    otherwise silently strip before intent classification ever sees them).
    """
    lemmas = set(_tokenize_and_lemmatize(message_text))
    message_lower = message_text.lower()

    for intent, keywords in _INTENT_PATTERNS.items():
        for kw in keywords:
            if kw in lemmas:
                return intent
            if re.search(r'\b' + re.escape(kw) + r'\b', message_lower):
                return intent

    return 'shopping_query'


# ---------------------------------------------------------------------------
# Slot extraction — lightweight, rule-based, updates ConversationSession.context_state
# ---------------------------------------------------------------------------

_WORD_NUMBERS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12,
}
_OCCASION_TRIGGER_PHRASES = {
    'birthday', 'party', 'wedding', 'graduation', 'family gathering',
    'gathering', 'christmas', 'new year', 'picnic', 'dinner', 'breakfast',
    'guest', 'visitor',
}


def _detect_occasion_mention(message_text):
    """
    Order-independent, prefix-based phrase matching — same approach
    already proven in advisor/conversational.py's _classify_intent, so
    plurals ("guests") and reordered phrasing are handled without
    needing an explicit variant for every word form. Deliberately
    conservative: only returns True on an actual occasion word, so
    ambiguous messages like "I need some food" are correctly left alone.
    """
    raw_tokens = re.findall(r'[a-z]+', message_text.lower())

    def _phrase_matches(phrase):
        words = phrase.split()
        return all(any(token.startswith(word) for token in raw_tokens) for word in words)

    return any(_phrase_matches(phrase) for phrase in _OCCASION_TRIGGER_PHRASES)

def _extract_slots(message_text, context_state):
    """
    Lightweight, rule-based slot-filling: looks for a budget figure and
    a family-size figure (numeral OR spelled-out word, e.g. "six people"),
    merges into the running context_state dict. Only updates a slot when
    a new value is actually found — never overwrites with nothing.
    """
    updated = dict(context_state)
    message_lower = message_text.lower()

    budget_match = re.search(r'\bLe\s?([\d,]+)|\b([\d,]{3,})\s?(?:le|leones)?\b', message_text, re.IGNORECASE)
    if budget_match:
        raw = (budget_match.group(1) or budget_match.group(2) or '').replace(',', '')
        if raw.isdigit():
            updated['budget'] = float(raw)

    family_match = re.search(r'(\d+)\s*(?:people|persons|guests)', message_text, re.IGNORECASE)
    if family_match:
        updated['family_size'] = int(family_match.group(1))
    else:
        for word, number in _WORD_NUMBERS.items():
            if re.search(r'\b' + word + r'\b\s*(?:people|persons|guests)', message_lower):
                updated['family_size'] = number
                break

    # Only updates shopping_purpose when THIS message actually mentions
    # an occasion — same "never overwrite with nothing" discipline as
    # budget/family_size above, so a later message with no occasion
    # words (e.g. just restating a number) doesn't erase context
    # established earlier in the conversation.
    if _detect_occasion_mention(message_text):
        updated['shopping_purpose'] = message_text

    return updated

# ---------------------------------------------------------------------------
# Routing — each branch calls an EXISTING function, never reimplements
# ---------------------------------------------------------------------------

def _handle_shopping_query(customer, message_text, context_state):
    """
    Constructs a throwaway ShoppingSession exactly the way Mode 1
    already does (see ai_commerce/views.py's natural-language mode),
    then calls the existing, unmodified generate_shopping_recommendations().
    """
    from .services import parse_natural_language_query

    parsed_intent = parse_natural_language_query(message_text)

    session = ShoppingSession.objects.create(
        customer=customer,
        mode='natural_language',
        raw_query=message_text,
        parsed_intent=parsed_intent,
        budget=context_state.get('budget'),
        family_size=context_state.get('family_size'),
        shopping_purpose=context_state.get('shopping_purpose', ''),
    )

    recommendations = generate_shopping_recommendations(session)

    if not recommendations:
        return "I couldn't find anything matching that in our catalogue right now. Could you try describing it differently?", 'shopping_assistant'

    top = recommendations[:3]
    lines = [f"Here are a few options based on what you're looking for:"]
    for rec in top:
        lines.append(f"- {rec.product.product_name} — Le {rec.product.online_price} ({rec.reasoning})")
    return "\n".join(lines), 'shopping_assistant'


def _handle_credit_question(customer):
    assessment = calculate_credit_recommendation(customer)

    if assessment.eligibility_status == 'eligible_increase':
        prefix = f"Yes — you're eligible for a credit purchase, and you actually qualify for a higher limit. "
    elif assessment.eligibility_status == 'maintain':
        prefix = f"Yes, you can purchase on credit within your current limit of Le {customer.credit_limit}. "
    else:
        prefix = "Your account needs a quick review before I can confirm a credit purchase. "

    return prefix + assessment.reasoning, 'credit_assistant'

def _handle_reorder_question(customer):
    suggestions = get_reorder_suggestions(customer, limit=3)
    if not suggestions:
        return "You don't have any previous orders yet for me to suggest a reorder from.", 'reorder'
    lines = ["Based on what you've ordered before, you might want to reorder:"]
    for s in suggestions:
        lines.append(f"- {s['product'].product_name} (ordered {s['times_ordered']} times)")
    return "\n".join(lines), 'reorder'


def _handle_insight_question(customer):
    from customer_insights.services import calculate_behaviour_metrics, classify_segment, generate_summary_text

    metrics = calculate_behaviour_metrics(customer)
    segment = classify_segment(customer, metrics)
    summary = generate_summary_text(customer, metrics, segment)
    return summary, 'customer_insights'


def _handle_delivery_question(customer, context_state):
    from delivery.models import DeliveryZone
    zones = DeliveryZone.objects.filter(is_active=True)
    if not zones.exists():
        return "I don't have any delivery zones configured to check right now.", 'delivery'
    lines = ["Here are our current delivery options:"]
    for z in zones:
        lines.append(f"- {z.zone_name}: Le {z.calculate_fee()}")
    return "\n".join(lines), 'delivery'


def _handle_greeting(customer):
    name = customer.full_name.split()[0] if customer else "there"
    return f"Hi {name}! I can help you find products, check your credit or delivery options, or reorder something you've bought before. What are you looking for?", 'greeting'


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_message(session, customer, message_text):
    """
    The single entry point called by the view layer (17d). Logs the
    user's turn, classifies intent, routes to the correct existing
    service, logs the assistant's reply, updates context_state, and
    returns the reply text.
    """
    ConversationTurn.objects.create(session=session, role='user', message_text=message_text)

    intent = _classify_intent(message_text)
    session.context_state = _extract_slots(message_text, session.context_state)

    backend = getattr(settings, 'AI_PROVIDER', 'rule_based')
    if backend != 'rule_based':
        from .llm_adapter import get_llm_response  # only imported when actually enabled
        reply_text, routed_to = get_llm_response(message_text, session.context_state, customer)
    else:
        if intent == 'credit_question':
            reply_text, routed_to = _handle_credit_question(customer)
        elif intent == 'reorder_question':
            reply_text, routed_to = _handle_reorder_question(customer)
        elif intent == 'insight_question':
            reply_text, routed_to = _handle_insight_question(customer)
        elif intent == 'delivery_question':
            reply_text, routed_to = _handle_delivery_question(customer, session.context_state)
        elif intent == 'greeting':
            reply_text, routed_to = _handle_greeting(customer)
        else:
            reply_text, routed_to = _handle_shopping_query(customer, message_text, session.context_state)

    session.save(update_fields=['context_state', 'last_message_at'])

    ConversationTurn.objects.create(
        session=session, role='assistant', message_text=reply_text,
        intent_detected=intent, routed_to=routed_to,
    )

    return reply_text