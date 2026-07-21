"""
ai_commerce/llm_adapter.py

Conversational Shopping AI's LLM integration point. Now a thin
consumer of the centralized core.ai_engine abstraction — provider
switching (rule_based/gemini/openai/anthropic) is governed entirely by
settings.AI_PROVIDER, not an ai_commerce-specific flag. All provider
API calls live in core/ai_engine.py; this file only builds the prompt
from already-correct rule-based data and asks the engine to rephrase.
"""
from django.conf import settings
from core.ai_engine import generate as ai_generate

SYSTEM_INSTRUCTION = (
    "You are a friendly retail shopping assistant for a Sierra Leonean store. "
    "Rephrase the given factual information conversationally in 2-3 sentences. "
    "Do not change any names, numbers, or prices — only rephrase, never invent facts."
)


def get_llm_response(message_text, context_state, customer):
    """
    Still delegates intent classification and data retrieval to the
    existing rule-based routing logic — the LLM only rephrases the
    result. Returns (reply_text, routed_to), same shape as every
    rule-based handler, so process_message() can call this
    interchangeably.
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
        f"A customer said: \"{message_text}\"\n\n"
        f"Here is the factually correct information to respond with (do not change any "
        f"names, numbers, or prices — only rephrase this more conversationally):\n\n{base_reply}"
    )

    rephrased = ai_generate(prompt, system_instruction=SYSTEM_INSTRUCTION)

    if rephrased:
        return rephrased, f"{routed_to}+{settings.AI_PROVIDER}"
    else:
        return base_reply, routed_to