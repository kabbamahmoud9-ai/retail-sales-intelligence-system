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
def _build_simple_prompt(message_text, base_reply):
    """Non-shopping intents keep the simpler rephrase-only pattern."""
    return (
        f"A customer said: \"{message_text}\"\n\n"
        f"Here is the factually correct information to respond with (do not change any "
        f"names, numbers, or prices — only rephrase this more conversationally):\n\n{base_reply}"
    )


def _build_shopping_prompt(customer, message_text, context_state):
    """
    Builds structured context for shopping questions: the already-
    selected real candidates, occasion/budget/guest-count context, and
    a backend-computed basket total/remaining/exceeds_budget verdict.
    The LLM only composes a narrative from this data — it never
    selects products, invents a price, or judges the budget itself.
    """
    from .services import parse_natural_language_query, generate_shopping_recommendations, build_validated_basket
    from .models import ShoppingSession

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
        base_reply = "I couldn't find anything matching that in our catalogue right now. Could you try describing it differently?"
        return base_reply, 'shopping_assistant', _build_simple_prompt(message_text, base_reply)

    basket = build_validated_basket(recommendations, budget=session.budget)

    item_lines = "\n".join(
        f"- {item['product'].product_name}: Le {item['price']} (stock: {item['stock']}) — {item['reasoning']}"
        for item in basket["items"]
    )

    base_reply = "Here are a few options based on what you're looking for:\n" + "\n".join(
        f"- {item['product'].product_name} — Le {item['price']} ({item['reasoning']})" for item in basket["items"]
    )

    context_notes = []
    if context_state.get('shopping_purpose'):
        context_notes.append(f"Occasion/purpose: {context_state['shopping_purpose']}")
    if context_state.get('family_size'):
        context_notes.append(f"Guests/household size: {context_state['family_size']}")
    if context_state.get('budget'):
        context_notes.append(f"Stated budget: Le {context_state['budget']}")

    budget_fact = ""
    if basket["budget"] is not None:
        if basket["exceeds_budget"]:
            budget_fact = (
                f"IMPORTANT FACT (already computed by the backend — do not recompute or "
                f"contradict this): this basket's total of Le {basket['total']} EXCEEDS the "
                f"customer's stated budget of Le {basket['budget']} by Le {abs(basket['remaining'])}. "
                f"You must say so honestly.\n\n"
            )
        else:
            budget_fact = (
                f"IMPORTANT FACT (already computed by the backend — do not recompute this): "
                f"this basket's total of Le {basket['total']} fits within the customer's "
                f"stated budget of Le {basket['budget']}, leaving Le {basket['remaining']} remaining.\n\n"
            )

    prompt = (
        f"A customer said: \"{message_text}\"\n\n"
        + ("\n".join(context_notes) + "\n\n" if context_notes else "")
        + f"Our catalogue system has already selected these REAL, currently available products "
        f"(do not add, remove, or substitute any item, and never change a name/price/stock figure):\n\n"
        f"{item_lines}\n\n"
        f"Real total for these items: Le {basket['total']}\n\n"
        + budget_fact
        + f"Write a natural, warm response that explains why this basket suits their request, "
        f"referencing the occasion/guest count/budget where relevant. Mention the real total."
    )

    return base_reply, 'shopping_assistant', prompt

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
        prompt = _build_simple_prompt(message_text, base_reply)
    elif intent == 'reorder_question':
        base_reply, routed_to = _handle_reorder_question(customer)
        prompt = _build_simple_prompt(message_text, base_reply)
    elif intent == 'insight_question':
        base_reply, routed_to = _handle_insight_question(customer)
        prompt = _build_simple_prompt(message_text, base_reply)
    elif intent == 'delivery_question':
        base_reply, routed_to = _handle_delivery_question(customer, context_state)
        prompt = _build_simple_prompt(message_text, base_reply)
    elif intent == 'greeting':
        base_reply, routed_to = _handle_greeting(customer)
        prompt = _build_simple_prompt(message_text, base_reply)
    else:
        base_reply, routed_to, prompt = _build_shopping_prompt(customer, message_text, context_state)

    rephrased = ai_generate(prompt, system_instruction=SYSTEM_INSTRUCTION)

    if rephrased:
        return rephrased, f"{routed_to}+{settings.AI_PROVIDER}"
    else:
        return base_reply, routed_to