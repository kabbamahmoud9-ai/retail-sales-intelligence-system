"""
advisor/llm_explainer.py

Optional LLM-powered natural-language explanation layer for the AI
Business Advisor, built on core.ai_engine. Never a source of truth —
only explains data that data_gathering.py already computed correctly.
"""
import json
from core.ai_engine import generate as ai_generate

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


def explain(base_reply, question_text, structured_context=None):
    """
    Rephrases/synthesizes an already-correct rule-based reply via the
    configured LLM provider. When structured_context is provided (cross-
    module diagnostic questions), the LLM gets the full structured data
    to genuinely synthesize across modules, not just rephrase one string.
    Returns None if the provider is rule_based, unconfigured, or fails.
    """
    if structured_context:
        context_json = json.dumps(structured_context, default=str, indent=2)
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