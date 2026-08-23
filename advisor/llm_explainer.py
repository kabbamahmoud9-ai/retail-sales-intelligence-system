"""
advisor/llm_explainer.py

Optional LLM-powered natural-language explanation layer for the AI
Business Advisor, built on core.ai_engine. Never a source of truth —
only explains data that data_gathering.py already computed correctly.
"""
import json

from core.ai_engine import generate as ai_generate
from customer_insights.models import CustomerInsightSnapshot
from delivery.models import DeliveryZone
from products.models import Product

SYSTEM_INSTRUCTION = (
    "You are a knowledgeable, professional Sierra Leonean retail business consultant "
    "speaking to a store manager. Explain the given business data clearly and "
    "encouragingly, in 3-5 sentences.\n\n"
    "CRITICAL RULES:\n"
    "- Never invent any figure, name, or fact beyond what is given.\n"
    "- Clearly distinguish observed facts from possible explanations from recommendations.\n"
    "- Use cautious language for anything not directly proven by the data, e.g. "
    "'the data suggests...', 'a possible explanation is...', 'this appears associated with...'.\n"
    "- If the given data is insufficient to explain something confidently, say so plainly "
    "rather than guessing — e.g. 'I don't have enough data to confidently determine this.'\n"
    "- End with 1-2 concrete recommendations, clearly labeled as recommendations."
)


def _json_default(obj):
    """
    Custom json.dumps(default=...) handler for explain()'s
    structured_context. data_gathering.py correctly returns real
    Django model instances embedded in that context -- the rule-based
    handlers in conversational.py depend on that exact shape
    (s.customer.full_name, z.zone_name, etc.) and are untouched here.

    Left to json.dumps(default=str), these instances would fall back
    to their __str__ -- which for CustomerInsightSnapshot and Product
    omits the very figures (churn_risk_score, quantity_in_stock) that
    make them relevant to the question being asked, and for
    DeliveryZone gives only the zone name with no context. This maps
    each to a small dict of only the fields the LLM path actually
    needs to reason about, without duplicating any business logic --
    every value here is a direct model field or property, never a
    recomputation.

    Anything not explicitly handled falls through to str(), preserving
    prior behavior for types not affected by this fix.
    """
    if isinstance(obj, CustomerInsightSnapshot):
        return {
            "customer_name": obj.customer.full_name,
            "segment": obj.get_segment_display(),
            "churn_risk_score": obj.churn_risk_score,
        }
    if isinstance(obj, DeliveryZone):
        return {
            "zone_name": obj.zone_name,
        }
    if isinstance(obj, Product):
        return {
            "product_name": obj.product_name,
            "quantity_in_stock": obj.quantity_in_stock,
        }
    return str(obj)


def explain(base_reply, question_text, structured_context=None):
    """
    Rephrases/synthesizes an already-correct rule-based reply via the
    configured LLM provider. When structured_context is provided (cross-
    module diagnostic questions), the LLM gets the full structured data
    to genuinely synthesize across modules, not just rephrase one string.
    Returns None if the provider is rule_based, unconfigured, or fails.
    """
    if structured_context:
        context_json = json.dumps(structured_context, default=_json_default, indent=2)
        prompt = (
            f"A store manager asked: \"{question_text}\"\n\n"
            f"Here is the REAL structured business data retrieved from the system "
            f"(do not invent anything beyond this):\n\n{context_json}\n\n"
            f"Synthesize this into a clear explanation, following the rules above."
        )
    else:
        prompt = (
            f"A store manager asked: \"{question_text}\"\n\n"
            f"Here is the factually correct business data to respond with:\n\n{base_reply}"
        )

    return ai_generate(prompt, system_instruction=SYSTEM_INSTRUCTION)