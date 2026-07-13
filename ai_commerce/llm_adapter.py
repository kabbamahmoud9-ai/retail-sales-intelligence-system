"""
ai_commerce/llm_adapter.py

OPTIONAL Gemini extension point for the Conversational Shopping AI
(Step 17). This file is NEVER imported unless settings.CONVERSATIONAL_AI_BACKEND
is explicitly set to 'gemini' — see conversational.py::process_message().
The system runs and is fully evaluable with zero external AI dependency
by default (Decision 28 preserved by construction, not just convention).

Scope of what Gemini is allowed to do here: understand the customer's
message and phrase a natural-language reply. It is explicitly NOT
permitted to invent product names, prices, credit limits, or any other
fact — this adapter still calls into the SAME existing service functions
conversational.py's rule-based path uses (get_candidate_products,
calculate_credit_recommendation, get_reorder_suggestions, etc.) to
retrieve real data, then asks Gemini only to phrase the natural-language
response around that real, already-correct data. This keeps the existing
services as the single source of truth even when this adapter is active
— Gemini augments phrasing/understanding, it never replaces business logic.
"""
import json
import requests
from django.conf import settings

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"


def _call_gemini(prompt):
    """
    Raw API call to Gemini's free-tier endpoint. Returns the text response,
    or None if the call fails for any reason (missing key, network error,
    unexpected response shape) — callers must handle a None gracefully by
    falling back to rule-based phrasing, never crashing the conversation.
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return None

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={api_key}",
            headers={'Content-Type': 'application/json'},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except (requests.RequestException, KeyError, IndexError, json.JSONDecodeError):
        return None


def get_llm_response(message_text, context_state, customer):
    """
    Public API — same (reply_text, routed_to) return shape as every
    rule-based handler in conversational.py, so process_message() can
    call this interchangeably with the rule-based path.

    Still delegates the ACTUAL intent classification and data retrieval
    to the existing rule-based routing logic — Gemini is only asked to
    rephrase the result more conversationally. This keeps a hard
    guarantee: no fact in the reply can be something Gemini invented,
    since the underlying data always comes from the same real service
    functions used in the rule-based path.
    """
    from .conversational import _classify_intent, _handle_shopping_query, _handle_credit_question, \
        _handle_reorder_question, _handle_insight_question, _handle_delivery_question, _handle_greeting

    intent = _classify_intent(message_text)

    if intent == 'credit_question':
        base_reply, routed_to = _handle_credit_question(customer)
    elif intent == 'reorder_question':
        base_reply, routed_to = _handle_reorder_question(customer)
    elif intent == 'insight_question':
        base_reply, routed_to = _handle_insight_question(customer)
    elif intent == 'delivery_question':
        base_reply, routed_to = _handle_delivery_question(customer, context_state)
    elif intent == 'greeting':
        base_reply, routed_to = _handle_greeting(customer)
    else:
        base_reply, routed_to = _handle_shopping_query(customer, message_text, context_state)

    prompt = (
        f"You are a friendly retail shopping assistant for a Sierra Leonean store. "
        f"A customer said: \"{message_text}\"\n\n"
        f"Here is the factually correct information to respond with (do not change any "
        f"names, numbers, or prices — only rephrase this more conversationally):\n\n"
        f"{base_reply}\n\n"
        f"Reply in a warm, natural, conversational tone in 2-3 sentences."
    )

    rephrased = _call_gemini(prompt)

    if rephrased:
        return rephrased, f"{routed_to}+gemini"
    else:
        # Graceful degrade: Gemini unreachable/misconfigured mid-conversation
        # -> fall back to the exact same rule-based reply, never break the chat.
        return base_reply, routed_to