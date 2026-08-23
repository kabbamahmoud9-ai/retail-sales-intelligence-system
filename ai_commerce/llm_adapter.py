"""
ai_commerce/llm_adapter.py

Conversational Shopping AI's LLM integration point. Now a thin
consumer of the centralized core.ai_engine abstraction — provider
switching (rule_based/gemini/openai/anthropic) is governed entirely by
settings.AI_PROVIDER, not an ai_commerce-specific flag. All provider
API calls live in core/ai_engine.py; this file only builds the prompt
from already-correct rule-based data and asks the engine to rephrase.

Shopping prompts are assembled in two steps:
  1. _build_structured_context() — pure assembly, no formatting. Reads
     already-computed data (parsed intent, session state, purchase
     signal, basket) into seven named sections (REQUEST, CONVERSATION,
     CUSTOMER, PRODUCTS, CALCULATIONS, EVIDENCE, INSTRUCTIONS). Adds
     no new business logic — every value here already exists
     elsewhere; this only organizes it.
  2. _render_prompt_from_context() — pure rendering, no computation.
     Turns the structured dict into the single prompt string every
     provider actually receives via core.ai_engine.generate().
This keeps the backend/LLM boundary explicit at the data-structure
level (CALCULATIONS is backend fact, never LLM-inferred) rather than
relying only on prose instructions to hold that line.
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


def _build_structured_context(customer, message_text, parsed_intent, context_state, basket):
    """
    Assembly layer only — no formatting, no new computation. Every
    value here is read from data that already exists elsewhere
    (parsed_intent from parse_natural_language_query(), context_state
    from the ShoppingSession slots, basket from build_validated_basket(),
    purchase signal from the same _get_customer_purchase_signal() the
    rule-based ranking already uses). Returns a plain dict; rendering
    into a prompt string happens separately in
    _render_prompt_from_context().
    """
    from .services import _get_customer_purchase_signal

    purchase_categories, _ = _get_customer_purchase_signal(customer)

    context = {
        "REQUEST": {
            "raw_message": message_text,
            "parsed_intent": parsed_intent,
        },
        "CONVERSATION": {
            "shopping_purpose": context_state.get('shopping_purpose', ''),
            "family_size": context_state.get('family_size'),
            "budget": context_state.get('budget'),
        },
        "PRODUCTS": [
            {
                "name": item['product'].product_name,
                "price": item['price'],
                "stock": item['stock'],
            }
            for item in basket["items"]
        ],
        "CALCULATIONS": {
            "total": basket["total"],
            "budget": basket["budget"],
            "remaining": basket["remaining"],
            "exceeds_budget": basket["exceeds_budget"],
        },
        "EVIDENCE": {
            item['product'].product_name: item['reasoning']
            for item in basket["items"]
        },
        "INSTRUCTIONS": [
            "Do not add, remove, or substitute any item.",
            "Never change a name, price, or stock figure.",
            "CALCULATIONS values are already computed by the backend — "
            "narrate them, never recompute or contradict them.",
            "Reference occasion, guest count, or budget where relevant.",
            "Mention the real total.",
        ],
    }

    if customer is not None:
        context["CUSTOMER"] = {
            "is_guest": False,
            "purchase_categories": sorted(purchase_categories),
        }
    else:
        context["CUSTOMER"] = {"is_guest": True}

    return context


def _render_prompt_from_context(context):
    """
    Rendering layer only — no computation, no business logic. Turns
    the structured dict from _build_structured_context() into the
    single prompt string sent to core.ai_engine.generate(). Every
    provider (rule_based never reaches this — see the early return in
    _build_shopping_prompt() — gemini/openai/anthropic) receives the
    same rendered string; provider selection itself is untouched.
    """
    lines = [f'A customer said: "{context["REQUEST"]["raw_message"]}"', ""]

    conv = context["CONVERSATION"]
    conv_notes = []
    if conv["shopping_purpose"]:
        conv_notes.append(f"Occasion/purpose: {conv['shopping_purpose']}")
    if conv["family_size"]:
        conv_notes.append(f"Guests/household size: {conv['family_size']}")
    if conv["budget"]:
        conv_notes.append(f"Stated budget: Le {conv['budget']}")
    if conv_notes:
        lines.append("CONVERSATION CONTEXT:")
        lines.extend(f"- {note}" for note in conv_notes)
        lines.append("")

    customer_info = context["CUSTOMER"]
    if not customer_info["is_guest"] and customer_info["purchase_categories"]:
        categories = ", ".join(customer_info["purchase_categories"])
        lines.append(f"CUSTOMER: Has purchased from {categories} before.")
        lines.append("")

    lines.append(
        "AVAILABLE PRODUCTS (these are the only REAL, currently available products — "
        "do not add, remove, or substitute any item, and never change a name/price/stock figure):"
    )
    for product in context["PRODUCTS"]:
        lines.append(f"- {product['name']}: Le {product['price']} (stock: {product['stock']})")
    lines.append("")

    calc = context["CALCULATIONS"]
    lines.append(f"Real total for these items: Le {calc['total']}")
    lines.append("")

    if calc["budget"] is not None:
        if calc["exceeds_budget"]:
            lines.append(
                f"IMPORTANT FACT (already computed by the backend — do not recompute or "
                f"contradict this): this basket's total of Le {calc['total']} EXCEEDS the "
                f"customer's stated budget of Le {calc['budget']} by Le {abs(calc['remaining'])}. "
                f"You must say so honestly."
            )
        else:
            lines.append(
                f"IMPORTANT FACT (already computed by the backend — do not recompute this): "
                f"this basket's total of Le {calc['total']} fits within the customer's "
                f"stated budget of Le {calc['budget']}, leaving Le {calc['remaining']} remaining."
            )
        lines.append("")

    if context["EVIDENCE"]:
        lines.append("WHY THESE ITEMS WERE SELECTED:")
        for name, reasoning in context["EVIDENCE"].items():
            lines.append(f"- {name}: {reasoning}")
        lines.append("")

    lines.append("INSTRUCTIONS:")
    lines.extend(f"- {instruction}" for instruction in context["INSTRUCTIONS"])
    lines.append("")
    lines.append(
        "Write a natural, warm response that explains why this basket suits their request, "
        "using the sections above."
    )

    return "\n".join(lines)


def _build_shopping_prompt(customer, message_text, context_state):
    """
    Builds structured context for shopping questions: the already-
    selected real candidates, occasion/budget/guest-count context, and
    a backend-computed basket total/remaining/exceeds_budget verdict.
    The LLM only composes a narrative from this data — it never
    selects products, invents a price, or judges the budget itself.

    Internally, context is assembled via _build_structured_context()
    and rendered via _render_prompt_from_context() — see module
    docstring. This function's signature and return shape are
    unchanged from before that split existed.
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

    base_reply = "Here are a few options based on what you're looking for:\n" + "\n".join(
        f"- {item['product'].product_name} — Le {item['price']} ({item['reasoning']})" for item in basket["items"]
    )

    structured_context = _build_structured_context(customer, message_text, parsed_intent, context_state, basket)
    prompt = _render_prompt_from_context(structured_context)

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